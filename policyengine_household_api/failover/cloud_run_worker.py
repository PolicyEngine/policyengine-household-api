from __future__ import annotations

import logging
from typing import Any, Callable

from flask import Flask, Response, jsonify, request
from policyengine_observability import current_operation
from policyengine_observability import operation
from policyengine_observability import record_error
from policyengine_observability import set_attribute
from werkzeug.exceptions import BadRequest

from policyengine_household_api.failover.dispatch_codec import (
    decode_dispatch_request,
    encode_dispatch_response,
)
from policyengine_household_api.failover.request_limits import (
    max_content_length_bytes,
)
from policyengine_household_api.modal_release.worker_dispatch import (
    dispatch_to_flask_app,
)
from policyengine_household_api.observability.flask import (
    configure_process_observability,
)
from policyengine_household_api.observability.flask import init_observability


logger = logging.getLogger(__name__)


def create_worker_app(
    *,
    flask_app: Flask | None = None,
    dispatcher: Callable[[Flask, dict[str, Any]], dict[str, Any]]
    | None = None,
) -> Flask:
    if flask_app is None:
        configure_process_observability(
            platform="google_cloud_run",
            service_role="cloud_run_worker",
        )
    app = Flask(__name__)
    # Reject oversized dispatch payloads before buffering them. The gateway
    # base64-encodes the original request body into this payload, so the cap
    # is the Cloud Run platform limit rather than the household body limit.
    app.config["MAX_CONTENT_LENGTH"] = max_content_length_bytes()
    household_app = flask_app or _load_household_app()
    init_observability(app, service_role="cloud_run_worker")
    dispatch = dispatcher or dispatch_to_flask_app

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.post("/_internal/dispatch")
    def dispatch_request() -> Response:
        with operation(
            "cloud_run_worker_dispatch",
            flavor="cloud_run_worker",
            platform="google_cloud_run",
            runtime_role="cloud_run_worker",
        ):
            try:
                payload = decode_dispatch_request(request.get_json(force=True))
                _set_dispatch_attribute(
                    "dispatch_method",
                    payload.get("method"),
                )
                _set_dispatch_attribute("dispatch_path", payload.get("path"))
                result = dispatch(household_app, payload)
                _set_dispatch_attribute(
                    "dispatch_status_code", result.get("status_code")
                )
                return jsonify(encode_dispatch_response(result))
            except (BadRequest, KeyError, TypeError, ValueError) as exc:
                record_error(
                    exc,
                    handled=True,
                    status_code=400,
                    include_stack=False,
                )
                response = jsonify(
                    {
                        "status": "error",
                        "code": "invalid_dispatch_payload",
                        "message": str(exc),
                    }
                )
                response.status_code = 400
                return response

    return app


def _load_household_app() -> Flask:
    from policyengine_household_api.api import app as household_app

    return household_app


def _set_dispatch_attribute(key: str, value: Any) -> None:
    set_attribute(key, value)
    try:
        active_operation = current_operation()
        if active_operation is not None:
            active_operation.set_attribute(key, value)
    except BaseException as exc:
        logger.warning("Failed to record dispatch attribute %s: %s", key, exc)
