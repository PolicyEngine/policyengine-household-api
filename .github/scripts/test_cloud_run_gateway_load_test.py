from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import sys
import threading
import time


def test_cloud_run_gateway_load_test_sends_concurrent_requests():
    handler = _handler()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    try:
        result = subprocess.run(
            [
                sys.executable,
                ".github/scripts/cloud_run_gateway_load_test.py",
                "--base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--auth-token",
                "token",
                "--requests",
                "8",
                "--concurrency",
                "4",
                "--expected-backend",
                "cloud_run",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert result.returncode == 0, result.stderr
    assert "requests=8 success=8 failed=0" in result.stdout
    assert "p90=" in result.stdout
    assert "observed_backends={'cloud_run': 8}" in result.stdout
    assert handler.max_active_requests > 1


def test_cloud_run_gateway_load_test_accepts_payload_file(tmp_path):
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps({"household": {"people": {}}}))
    handler = _handler()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    try:
        result = subprocess.run(
            [
                sys.executable,
                ".github/scripts/cloud_run_gateway_load_test.py",
                "--base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--payload-file",
                str(payload_file),
                "--requests",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert result.returncode == 0, result.stderr
    assert handler.last_payload == {"household": {"people": {}}}


def _handler():
    class Handler(BaseHTTPRequestHandler):
        active_requests = 0
        max_active_requests = 0
        last_payload = None
        lock = threading.Lock()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            type(self).last_payload = json.loads(body.decode("utf-8"))
            with type(self).lock:
                type(self).active_requests += 1
                type(self).max_active_requests = max(
                    type(self).max_active_requests,
                    type(self).active_requests,
                )

            try:
                time.sleep(0.05)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-PolicyEngine-Backend", "cloud_run")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            finally:
                with type(self).lock:
                    type(self).active_requests -= 1

        def log_message(self, format, *args):
            return

    return Handler
