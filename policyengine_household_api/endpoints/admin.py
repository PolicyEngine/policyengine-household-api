"""
Staff-only admin endpoints for the developer portal.

These are gated by the ``policyengine-staff`` JWT scope: any caller
without it gets 403. The portal uses them to power the "All partners"
overview and the test-case activity feed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from flask import Response, request
from sqlalchemy import func

from policyengine_household_api.data.analytics_setup import (
    db,
    is_analytics_enabled,
    is_analytics_schema_ready,
)
from policyengine_household_api.data.models import TestCase, TestCaseAudit
from policyengine_household_api.endpoints.test_cases import (
    _verified_token_claims,
    _bearer_token_from_header,
    _has_scope,
)
from policyengine_household_api.decorators.auth import STAFF_SCOPE


DEFAULT_ACTIVITY_LIMIT = 100
MAX_ACTIVITY_LIMIT = 1000


def list_partners() -> Response:
    """Return one row per partner client_id seen in the test_cases
    table, with last activity timestamp + case count."""
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    forbidden = _staff_only()
    if forbidden is not None:
        return forbidden

    rows = (
        db.session.query(
            TestCase.client_id,
            func.count(TestCase.id).label("test_case_count"),
            func.max(TestCase.updated_at).label("last_updated"),
        )
        .group_by(TestCase.client_id)
        .order_by(func.max(TestCase.updated_at).desc())
        .all()
    )

    return _json_response(
        {
            "status": "ok",
            "message": None,
            "partners": [
                {
                    "client_id": row.client_id,
                    "test_case_count": int(row.test_case_count or 0),
                    "last_activity": _datetime_to_json(row.last_updated),
                }
                for row in rows
            ],
        }
    )


def list_activity() -> Response:
    """Return recent test_case_audits rows. Most useful as a
    chronological feed of "Acme created/updated/deleted X" — drives
    the staff activity page."""
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    forbidden = _staff_only()
    if forbidden is not None:
        return forbidden

    try:
        limit = _parse_limit(request.args.get("limit"))
    except ValueError as e:
        return _json_response(
            {"status": "error", "message": str(e)}, status=400
        )

    client_id = request.args.get("client_id")
    query = db.session.query(TestCaseAudit).order_by(TestCaseAudit.id.desc())
    if client_id:
        query = query.filter(TestCaseAudit.client_id == client_id)
    rows = query.limit(limit).all()

    return _json_response(
        {
            "status": "ok",
            "message": None,
            "events": [
                {
                    "id": row.id,
                    "test_case_id": row.test_case_id,
                    "client_id": row.client_id,
                    "actor_client_id": row.actor_client_id,
                    "action": row.action,
                    "name_snapshot": row.name_snapshot,
                    "occurred_at": _datetime_to_json(row.occurred_at),
                }
                for row in rows
            ],
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _staff_only() -> Response | None:
    claims = _verified_token_claims(_bearer_token_from_header())
    if claims is None:
        return _json_response(
            {"status": "error", "message": "Could not identify caller."},
            status=401,
        )
    if not _has_scope(claims, STAFF_SCOPE):
        return _json_response(
            {
                "status": "error",
                "message": "This endpoint requires the policyengine-staff scope.",
            },
            status=403,
        )
    return None


def _storage_error_response() -> Response | None:
    if not is_analytics_enabled():
        return _json_response(
            {
                "status": "error",
                "message": "Test-case storage is not enabled for this API instance.",
            },
            status=503,
        )
    if not is_analytics_schema_ready():
        return _json_response(
            {"status": "error", "message": "Test-case storage is not ready."},
            status=503,
        )
    return None


def _parse_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_ACTIVITY_LIMIT
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("`limit` must be an integer")
    if value < 1 or value > MAX_ACTIVITY_LIMIT:
        raise ValueError(
            f"`limit` must be between 1 and {MAX_ACTIVITY_LIMIT}; got {value}"
        )
    return value


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_response(body: dict[str, Any], status: int = 200) -> Response:
    return Response(
        json.dumps(body).encode("utf-8"),
        status=status,
        mimetype="application/json",
    )
