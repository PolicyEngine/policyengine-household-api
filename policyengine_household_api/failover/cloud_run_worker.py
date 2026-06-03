from __future__ import annotations

import json
import os
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


WORKER_CHANNEL_ENV = "HOUSEHOLD_FAILOVER_CHANNEL"
WORKER_PACKAGE_VERSIONS_ENV = "HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON"


def create_worker_app(
    *,
    flask_app: Flask | None = None,
    dispatcher: Callable[[Flask, dict[str, Any]], dict[str, Any]] | None = None,
    channel: str | None = None,
    package_versions: dict[str, str] | None = None,
) -> Flask:
    app = Flask(__name__)
    household_app = flask_app or _load_household_app()
    dispatch = dispatcher or dispatch_to_flask_app
    resolved_channel = channel or os.getenv(WORKER_CHANNEL_ENV, "unknown")
    resolved_versions = package_versions or _package_versions_from_env()

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/_internal/health")
    def health_check() -> Response:
        return jsonify(
            {
                "status": "ok",
                "backend": "cloud_run",
                "channel": resolved_channel,
                "package_versions": resolved_versions,
            }
        )

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


def _package_versions_from_env() -> dict[str, str]:
    raw_value = os.getenv(WORKER_PACKAGE_VERSIONS_ENV, "{}")
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        country: version
        for country, version in parsed.items()
        if isinstance(country, str) and isinstance(version, str)
    }
