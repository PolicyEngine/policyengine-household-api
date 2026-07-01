from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import sys
import threading
import time


def test_cloud_run_prewarm_full_calc_succeeds_after_retry():
    handler = _handler(status_codes=[503, 200])
    server, thread = _start_server(handler)

    try:
        result = subprocess.run(
            [
                sys.executable,
                ".github/scripts/cloud_run_prewarm_full_calc_via_gateway.py",
                "current",
                "--base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--auth-token",
                "token",
                "--max-attempts",
                "5",
                "--max-elapsed-seconds",
                "5",
                "--retry-delay-seconds",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert result.returncode == 0, result.stderr
    assert "attempt=1 status=503" in result.stdout
    assert "attempt=2 status=200" in result.stdout
    assert "Cloud Run gateway prewarm succeeded" in result.stdout
    assert len(handler.calculate_payloads) == 2
    assert handler.calculate_payloads[-1]["version"] == "current"
    assert handler.authorization_headers == ["Bearer token", "Bearer token"]


def test_cloud_run_prewarm_full_calc_rejects_slow_success():
    handler = _handler(status_codes=[200], sleep_seconds=0.05)
    server, thread = _start_server(handler)

    try:
        result = subprocess.run(
            [
                sys.executable,
                ".github/scripts/cloud_run_prewarm_full_calc_via_gateway.py",
                "frontier",
                "--base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--auth-token",
                "token",
                "--max-attempts",
                "1",
                "--max-elapsed-seconds",
                "0.001",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert result.returncode == 1
    assert "attempt=1 status=200" in result.stdout
    assert "Cloud Run gateway prewarm failed" in result.stderr
    assert len(handler.calculate_payloads) == 1
    assert handler.calculate_payloads[0]["version"] == "frontier"


def _start_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread


def _handler(status_codes: list[int], sleep_seconds: float = 0):
    class Handler(BaseHTTPRequestHandler):
        calculate_payloads = []
        authorization_headers = []

        def do_GET(self):
            if self.path != "/versions/us":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "current": "1.732.0",
                        "frontier": "1.744.0",
                    }
                ).encode("utf-8")
            )

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            type(self).calculate_payloads.append(
                json.loads(body.decode("utf-8"))
            )
            type(self).authorization_headers.append(
                self.headers.get("Authorization")
            )
            if sleep_seconds:
                time.sleep(sleep_seconds)

            index = len(type(self).calculate_payloads) - 1
            status_code = status_codes[min(index, len(status_codes) - 1)]
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-PolicyEngine-Backend", "modal")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "result": {"people": {}}}')

        def log_message(self, format, *args):
            return

    return Handler
