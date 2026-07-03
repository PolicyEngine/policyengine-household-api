from __future__ import annotations

import logging
from typing import Callable

from flask import Flask, Response, jsonify, request
from policyengine_observability import operation, record_error, set_attribute
from pydantic import ValidationError
from werkzeug.exceptions import BadRequest

from policyengine_household_api.analytics.events import CalculateAnalyticsEvent
from policyengine_household_api.analytics.persistence import (
    record_calculate_analytics_event,
)
from policyengine_household_api.data.analytics_setup import (
    initialize_analytics_db_if_enabled,
)
from policyengine_household_api.failover.request_limits import (
    max_content_length_bytes,
)
from policyengine_household_api.observability.flask import (
    configure_process_observability,
    init_observability,
)

logger = logging.getLogger(__name__)


def create_analytics_writer_app(
    *,
    persist_event: Callable[[CalculateAnalyticsEvent], None] | None = None,
    initialize_db: bool = True,
) -> Flask:
    if initialize_db:
        configure_process_observability(
            platform="google_cloud_run",
            service_role="cloud_run_analytics_writer",
        )
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = max_content_length_bytes()
    init_observability(app, service_role="cloud_run_analytics_writer")
    if initialize_db:
        initialize_analytics_db_if_enabled(app)
    persist = persist_event or record_calculate_analytics_event

    @app.get("/liveness_check")
    def liveness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.get("/readiness_check")
    def readiness_check() -> Response:
        return Response("OK", status=200, mimetype="text/plain")

    @app.post("/internal/analytics/calculate/write")
    def write_calculate_analytics() -> Response:
        with operation(
            "cloud_run_analytics_write",
            flavor="cloud_run_analytics_writer",
            platform="google_cloud_run",
            runtime_role="cloud_run_analytics_writer",
        ):
            try:
                event = CalculateAnalyticsEvent.model_validate(
                    request.get_json(force=True)
                )
                set_attribute("request_uuid", event.context.request_uuid)
                set_attribute("analytics_schema_version", event.schema_version)
                persist(event)
                return jsonify(
                    {
                        "status": "ok",
                        "request_uuid": event.context.request_uuid,
                    }
                )
            except (BadRequest, TypeError, ValueError, ValidationError) as exc:
                record_error(
                    exc,
                    handled=True,
                    status_code=400,
                    include_stack=False,
                )
                response = jsonify(
                    {
                        "status": "error",
                        "code": "invalid_analytics_event",
                        "message": str(exc),
                    }
                )
                response.status_code = 400
                return response
            except Exception as exc:
                logger.warning(
                    "Failed to persist calculate analytics event.",
                    exc_info=True,
                )
                record_error(
                    exc,
                    handled=True,
                    status_code=500,
                    include_stack=True,
                )
                response = jsonify(
                    {
                        "status": "error",
                        "code": "analytics_write_failed",
                        "message": "Analytics write failed.",
                    }
                )
                response.status_code = 500
                return response

    return app
