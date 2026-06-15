from flask import Flask, jsonify

from policyengine_household_api.failover.cloud_run_worker import (
    create_worker_app,
)
from policyengine_household_api.failover.dispatch_codec import (
    decode_dispatch_response,
    encode_dispatch_request,
)
from policyengine_household_api.modal_release.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
)


def _household_app():
    app = Flask(__name__)

    @app.post("/us/calculate")
    def calculate():
        return jsonify({"status": "ok"})

    @app.get("/fail")
    def fail():
        return jsonify({"status": "error"}), 500

    return app


def test_worker_liveness_check():
    app = create_worker_app(flask_app=_household_app())

    response = app.test_client().get("/liveness_check")

    assert response.status_code == 200
    assert response.text == "OK"


def test_worker_dispatches_payload_to_household_app():
    app = create_worker_app(flask_app=_household_app())
    payload = encode_dispatch_request(
        {
            "method": "POST",
            "path": "/us/calculate",
            "headers": {"Content-Type": "application/json"},
            "body": b'{"household": {}}',
            MODAL_ROUTING_PAYLOAD_KEY: {
                "requested_version": "current",
                "resolved_channel": "current",
            },
        }
    )

    response = app.test_client().post("/_internal/dispatch", json=payload)

    assert response.status_code == 200
    result = decode_dispatch_response(response.get_json())
    assert result["status_code"] == 200
    assert result["body"] == b'{"status":"ok"}\n'


def test_worker_preserves_app_level_500_as_dispatch_result():
    app = create_worker_app(flask_app=_household_app())
    payload = encode_dispatch_request(
        {"method": "GET", "path": "/fail", "headers": {}, "body": b""}
    )

    response = app.test_client().post("/_internal/dispatch", json=payload)

    assert response.status_code == 200
    result = decode_dispatch_response(response.get_json())
    assert result["status_code"] == 500


def test_worker_rejects_invalid_dispatch_payload():
    app = create_worker_app(flask_app=_household_app())

    response = app.test_client().post("/_internal/dispatch", json=[])

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_dispatch_payload"


def test_worker_rejects_dispatch_payload_over_limit(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_FAILOVER_MAX_CONTENT_LENGTH", "1024")
    app = create_worker_app(flask_app=_household_app())

    response = app.test_client().post(
        "/_internal/dispatch",
        data=b"x" * 4096,
        content_type="application/json",
    )

    assert response.status_code == 413
