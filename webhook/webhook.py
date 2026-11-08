import json
from http.server import BaseHTTPRequestHandler, HTTPServer

received = []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        for alert in body.get("alerts", []):
            entry = {
                "status": alert["status"],
                "alertname": alert["labels"].get("alertname"),
                "severity": alert["labels"].get("severity"),
                "summary": alert["annotations"].get("summary"),
            }
            received.append(entry)
            print(f"ALERT {json.dumps(entry)}", flush=True)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        payload = json.dumps(received[-50:]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 5001), Handler).serve_forever()
