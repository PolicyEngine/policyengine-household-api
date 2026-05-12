from __future__ import annotations

import os
from typing import Callable

from flask import Response, request


def install_gateway_guard(app) -> None:
    """Reject direct worker traffic when a gateway secret is configured."""

    @app.before_request
    def require_gateway_secret() -> Response | None:
        expected_secret = os.getenv("HOUSEHOLD_MODAL_GATEWAY_SECRET")
        if not expected_secret:
            return None

        supplied_secret = request.headers.get(
            "X-Household-Modal-Gateway-Secret"
        )
        if supplied_secret == expected_secret:
            return None

        return Response(
            '{"status":"error","message":"Worker endpoint is private"}',
            status=403,
            mimetype="application/json",
        )


def guarded_wsgi_app(app_factory: Callable[[], object]) -> object:
    app = app_factory()
    install_gateway_guard(app)
    return app
