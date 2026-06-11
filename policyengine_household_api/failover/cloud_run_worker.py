from __future__ import annotations

from typing import Any, Callable

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import BadRequest

from policyengine_household_api.failover.dispatch_codec import (
    decode_dispatch_request,
    encode_dispatch_response,
)
from policyengine_household_api.modal_release.worker_dispatch import (
    dispatch_to_flask_app,
)


def create_worker_app(
    *,
    flask_app: Flask | None = None,
    dispatcher: Callable[[Flask, dict[str, Any]], dict[str, Any]]
    | None = None,
) -> Flask:
    app = Flask(__name__)
    household_app = flask_app or _load_household_app()
    dispatch = dispatcher or dispatch_to_flask_app

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.post("/_internal/dispatch")
    def dispatch_request() -> Response:
        try:
            payload = decode_dispatch_request(request.get_json(force=True))
            result = dispatch(household_app, payload)
            return jsonify(encode_dispatch_response(result))
        except (BadRequest, KeyError, TypeError, ValueError) as exc:
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
