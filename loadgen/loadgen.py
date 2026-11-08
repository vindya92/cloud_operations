import os
import random
import threading
import time

import requests
from security import create_access_token

TARGET = os.getenv("TARGET", "http://app:8000")
WORKERS = int(os.getenv("WORKERS", "4"))
THINK_MS = int(os.getenv("THINK_MS", "300"))


def api_headers():
    return {"Authorization": f"Bearer {create_access_token('load-generator')}"}

ACTIONS = [
    (70, lambda: requests.get(f"{TARGET}/api/orders", timeout=10)),
    (20, lambda: requests.post(f"{TARGET}/api/orders", headers=api_headers(), timeout=10)),
    (5, lambda: requests.get(f"{TARGET}/api/slow", timeout=10)),
    (3, lambda: requests.get(f"{TARGET}/health", timeout=10)),
    (2, lambda: requests.get(f"{TARGET}/api/error", timeout=10)),
]


def worker():
    weights = [w for w, _ in ACTIONS]
    while True:
        _, action = random.choices(ACTIONS, weights=weights)[0]
        try:
            action()
        except requests.RequestException:
            time.sleep(1)
        time.sleep(random.uniform(0, 2 * THINK_MS / 1000))


if __name__ == "__main__":
    for _ in range(WORKERS):
        threading.Thread(target=worker, daemon=True).start()
    while True:
        time.sleep(60)
