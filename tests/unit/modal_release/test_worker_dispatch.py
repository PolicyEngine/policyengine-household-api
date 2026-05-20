from flask import Flask, Response, request

from policyengine_household_api.modal_release.worker_dispatch import (
    dispatch_to_flask_app,
)
from policyengine_household_api.utils.modal_routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
    REQUESTED_VERSION_ENVIRON_KEY,
    RESOLVED_CHANNEL_ENVIRON_KEY,
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


def test_dispatch_to_flask_app_sets_modal_routing_environ():
    app = Flask(__name__)

    @app.post("/us/calculate")
    def calculate():
        return {
            "requested_version": request.environ[
                REQUESTED_VERSION_ENVIRON_KEY
            ],
            "resolved_channel": request.environ[RESOLVED_CHANNEL_ENVIRON_KEY],
        }

    response = dispatch_to_flask_app(
        app,
        {
            "method": "POST",
            "path": "us/calculate",
            "query_string": "",
            "headers": {"Content-Type": "application/json"},
            "body": b'{"household": {}}',
            MODAL_ROUTING_PAYLOAD_KEY: {
                "requested_version": "1.691.1",
                "resolved_channel": "frontier",
            },
        },
    )

    assert response["status_code"] == 200
    assert b'"requested_version":"1.691.1"' in response["body"]
    assert b'"resolved_channel":"frontier"' in response["body"]


def test_dispatch_to_flask_app_ignores_invalid_modal_routing_payload():
    app = Flask(__name__)

    @app.post("/us/calculate")
    def calculate():
        return {
            "requested_version_present": (
                REQUESTED_VERSION_ENVIRON_KEY in request.environ
            ),
            "resolved_channel_present": (
                RESOLVED_CHANNEL_ENVIRON_KEY in request.environ
            ),
        }

    response = dispatch_to_flask_app(
        app,
        {
            "method": "POST",
            "path": "us/calculate",
            "query_string": "",
            "headers": {"Content-Type": "application/json"},
            "body": b'{"household": {}}',
            MODAL_ROUTING_PAYLOAD_KEY: {
                "requested_version": "frontier",
                "resolved_channel": "stable",
            },
        },
    )

    assert response["status_code"] == 200
    assert b'"requested_version_present":false' in response["body"]
    assert b'"resolved_channel_present":false' in response["body"]


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
