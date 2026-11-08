import json
import logging
import os
import random
import socket
import sys
import time
import uuid

import redis
from flask import Flask, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from security import verify_access_token

INSTANCE = socket.gethostname()
# One log file per replica so concurrent writers never interleave lines.
LOG_FILE = os.path.join(os.getenv("LOG_DIR", "/var/log/app"), f"{INSTANCE}.log")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "instance": INSTANCE,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "ctx", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def build_logger():
    logger = logging.getLogger("orders-api")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    handlers = [logging.StreamHandler(sys.stdout)]
    if os.path.isdir(os.path.dirname(LOG_FILE)):
        handlers.append(logging.FileHandler(LOG_FILE))
    for handler in handlers:
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


log = build_logger()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
IN_FLIGHT = Gauge("http_requests_in_flight", "Requests currently being served")
ORDERS = Counter("orders_created_total", "Orders created")

# Shared state lives in Redis so every replica behind the load balancer sees the same data.
store = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, decode_responses=True)

if store.set("orders:seeded", 1, nx=True):
    for i in range(1, 6):
        store.rpush("orders", json.dumps({"id": i, "item": f"item-{i}", "qty": random.randint(1, 5)}))
    store.set("orders:next_id", 5)

CHAOS_DEFAULTS = {"error_rate": 0.0, "latency_ms": 0, "cause": "db_pool_exhausted"}


def get_chaos():
    raw = store.hgetall("chaos")
    return {
        "error_rate": float(raw.get("error_rate", CHAOS_DEFAULTS["error_rate"])),
        "latency_ms": int(raw.get("latency_ms", CHAOS_DEFAULTS["latency_ms"])),
        "cause": raw.get("cause", CHAOS_DEFAULTS["cause"]),
    }


def simulate_work():
    """Simulate backend work and apply any injected faults."""
    chaos = get_chaos()
    time.sleep(random.uniform(0.02, 0.08) + chaos["latency_ms"] / 1000)
    if random.random() < chaos["error_rate"]:
        raise RuntimeError(f"backend failure: {chaos['cause']}")


@app.before_request
def start_timer():
    g.start = time.time()
    g.request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    if request.path != "/metrics":
        IN_FLIGHT.inc()


@app.after_request
def record(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.path == "/metrics":
        return response
    IN_FLIGHT.dec()
    endpoint = request.url_rule.rule if request.url_rule else "unmatched"
    duration = time.time() - g.start
    REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
    LATENCY.labels(endpoint).observe(duration)
    response.headers["X-Request-ID"] = g.request_id
    response.headers["X-Served-By"] = INSTANCE
    level = logging.ERROR if response.status_code >= 500 else logging.INFO
    log.log(
        level,
        "request completed",
        extra={
            "ctx": {
                "request_id": g.request_id,
                "method": request.method,
                "endpoint": endpoint,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 1),
            }
        },
    )
    return response


@app.before_request
def require_write_token():
    if request.method != "POST" or request.path not in {"/api/orders", "/chaos"}:
        return None
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return jsonify(error="unauthorized"), 401
    try:
        g.token_claims = verify_access_token(token)
    except Exception:
        return jsonify(error="unauthorized"), 401
    return None


@app.errorhandler(Exception)
def handle_error(exc):
    log.error(
        str(exc),
        exc_info=exc,
        extra={"ctx": {"request_id": g.get("request_id"), "endpoint": request.path}},
    )
    return jsonify(error="internal error", request_id=g.get("request_id")), 500


@app.get("/")
def index():
    return jsonify(service="orders-api", status="running")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/api/orders")
def list_orders():
    simulate_work()
    return jsonify([json.loads(o) for o in store.lrange("orders", 0, -1)])


@app.post("/api/orders")
def create_order():
    simulate_work()
    order_id = store.incr("orders:next_id")
    order = {"id": order_id, "item": f"item-{order_id}", "qty": 1}
    store.rpush("orders", json.dumps(order))
    store.ltrim("orders", -1000, -1)
    ORDERS.inc()
    return jsonify(order), 201


@app.get("/api/slow")
def slow():
    time.sleep(random.uniform(1, 3))
    return jsonify(status="slow but ok")


@app.get("/api/error")
def error():
    raise RuntimeError("deliberate failure for debugging practice")


@app.route("/chaos", methods=["GET", "POST"])
def chaos_control():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        chaos = {
            "error_rate": min(max(float(body.get("error_rate", 0)), 0), 1),
            "latency_ms": max(int(body.get("latency_ms", 0)), 0),
            "cause": str(body.get("cause", CHAOS_DEFAULTS["cause"])),
        }
        store.hset("chaos", mapping=chaos)
        log.warning("chaos settings changed", extra={"ctx": dict(chaos)})
    return jsonify(get_chaos())


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
