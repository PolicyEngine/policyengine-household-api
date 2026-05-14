from flask import Flask, Response, request

from policyengine_household_api.modal_release.worker_dispatch import (
    dispatch_to_flask_app,
)


def test_dispatch_to_flask_app_preserves_request_shape():
    app = Flask(__name__)

    @app.post("/us/calculate")
    def calculate():
        return {
            "auth": request.headers["Authorization"],
            "query": request.args["trace"],
            "body": request.get_json(),
        }

    response = dispatch_to_flask_app(
        app,
        {
            "method": "POST",
            "path": "us/calculate",
            "query_string": "trace=true",
            "headers": {
                "Authorization": "Bearer token",
                "Content-Type": "application/json",
            },
            "body": b'{"household": {}}',
        },
    )

    assert response["status_code"] == 200
    assert b'"auth":"Bearer token"' in response["body"]
    assert b'"query":"true"' in response["body"]
    assert b'"body":{"household":{}}' in response["body"]


def test_dispatch_to_flask_app_removes_hop_by_hop_response_headers():
    app = Flask(__name__)

    @app.get("/liveness_check")
    def liveness_check():
        return Response(
            "OK",
            headers={
                "Connection": "close",
                "Content-Length": "2",
                "X-Diagnostic": "kept",
            },
        )

    response = dispatch_to_flask_app(
        app,
        {
            "method": "GET",
            "path": "/liveness_check",
            "query_string": "",
            "headers": {},
            "body": b"",
        },
    )

    response_headers = dict(response["headers"])
    assert "Connection" not in response_headers
    assert "Content-Length" not in response_headers
    assert response_headers["X-Diagnostic"] == "kept"
