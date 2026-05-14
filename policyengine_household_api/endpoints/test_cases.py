"""
Per-partner saved test-case storage.

Each partner client_id owns a library of household payloads. CRUD is
scoped to the caller's authenticated client_id. Phase 2 will add an
``as_client_id`` query param honored only for callers carrying the
``policyengine-staff`` scope.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from flask import Response, request

from policyengine_household_api.data.analytics_setup import (
    db,
    is_analytics_enabled,
    is_analytics_schema_ready,
)
from policyengine_household_api.data.models import TestCase, TestCaseAudit
from policyengine_household_api.decorators.analytics import (
    _verified_sub_claim,
)


MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 4096
# Cap individual payloads to keep one-row writes bounded; the API rejects
# household payloads larger than MAX_CONTENT_LENGTH at the request layer
# already, but storage cost is per-row so add a tighter ceiling here.
MAX_PAYLOAD_BYTES = 256 * 1024  # 256 KiB


def list_test_cases() -> Response:
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    client_id = _resolve_caller_client_id()
    if client_id is None:
        return _auth_error()

    rows = (
        db.session.query(TestCase)
        .filter(TestCase.client_id == client_id)
        .order_by(TestCase.updated_at.desc())
        .all()
    )
    return _json_response(
        {
            "status": "ok",
            "message": None,
            "test_cases": [_serialize(row) for row in rows],
        }
    )


def get_test_case(test_case_id: int) -> Response:
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    client_id = _resolve_caller_client_id()
    if client_id is None:
        return _auth_error()

    row = db.session.get(TestCase, test_case_id)
    if row is None or row.client_id != client_id:
        return _not_found()

    return _json_response(
        {"status": "ok", "message": None, "test_case": _serialize(row)}
    )


def create_test_case() -> Response:
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    client_id = _resolve_caller_client_id()
    if client_id is None:
        return _auth_error()

    try:
        body = _parse_body(request.get_data())
    except ValueError as e:
        return _validation_error(str(e))

    name = body.get("name")
    description = body.get("description")
    payload = body.get("payload")
    try:
        _validate_writable_fields(name, description, payload)
    except ValueError as e:
        return _validation_error(str(e))

    now = datetime.now(timezone.utc)
    row = TestCase(
        client_id=client_id,
        name=name,
        description=description,
        payload=payload,
        created_at=now,
        updated_at=now,
    )
    db.session.add(row)
    db.session.flush()  # populate row.id
    _record_audit(
        test_case_id=row.id,
        client_id=client_id,
        actor_client_id=client_id,
        action="created",
        name_snapshot=name,
        occurred_at=now,
    )
    db.session.commit()

    return _json_response(
        {"status": "ok", "message": None, "test_case": _serialize(row)},
        status=201,
    )


def update_test_case(test_case_id: int) -> Response:
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    client_id = _resolve_caller_client_id()
    if client_id is None:
        return _auth_error()

    row = db.session.get(TestCase, test_case_id)
    if row is None or row.client_id != client_id:
        return _not_found()

    try:
        body = _parse_body(request.get_data())
    except ValueError as e:
        return _validation_error(str(e))

    if "name" in body:
        name = body["name"]
        try:
            _validate_name(name)
        except ValueError as e:
            return _validation_error(str(e))
        row.name = name
    if "description" in body:
        description = body["description"]
        try:
            _validate_description(description)
        except ValueError as e:
            return _validation_error(str(e))
        row.description = description
    if "payload" in body:
        payload = body["payload"]
        try:
            _validate_payload(payload)
        except ValueError as e:
            return _validation_error(str(e))
        row.payload = payload

    now = datetime.now(timezone.utc)
    row.updated_at = now
    _record_audit(
        test_case_id=row.id,
        client_id=client_id,
        actor_client_id=client_id,
        action="updated",
        name_snapshot=row.name,
        occurred_at=now,
    )
    db.session.commit()

    return _json_response(
        {"status": "ok", "message": None, "test_case": _serialize(row)}
    )


def delete_test_case(test_case_id: int) -> Response:
    storage_error = _storage_error_response()
    if storage_error is not None:
        return storage_error

    client_id = _resolve_caller_client_id()
    if client_id is None:
        return _auth_error()

    row = db.session.get(TestCase, test_case_id)
    if row is None or row.client_id != client_id:
        return _not_found()

    name_snapshot = row.name
    db.session.delete(row)
    _record_audit(
        test_case_id=test_case_id,
        client_id=client_id,
        actor_client_id=client_id,
        action="deleted",
        name_snapshot=name_snapshot,
        occurred_at=datetime.now(timezone.utc),
    )
    db.session.commit()

    return _json_response({"status": "ok", "message": None})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
            {
                "status": "error",
                "message": "Test-case storage is not ready.",
            },
            status=503,
        )
    return None


def _resolve_caller_client_id() -> str | None:
    """Extract and verify the bearer-token sub claim, normalize the
    Auth0 ``@clients`` suffix, and return the resulting client_id."""
    try:
        auth_header = str(request.authorization)
        token = auth_header.split(" ")[1]
    except Exception:
        return None
    sub = _verified_sub_claim(token)
    if sub is None:
        return None
    suffix = "@clients"
    return sub[: -len(suffix)] if sub.endswith(suffix) else sub


def _record_audit(
    *,
    test_case_id: int,
    client_id: str,
    actor_client_id: str,
    action: str,
    name_snapshot: str | None,
    occurred_at: datetime,
) -> None:
    db.session.add(
        TestCaseAudit(
            test_case_id=test_case_id,
            client_id=client_id,
            actor_client_id=actor_client_id,
            action=action,
            name_snapshot=name_snapshot,
            occurred_at=occurred_at,
        )
    )


def _serialize(row: TestCase) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "payload": row.payload,
        "created_at": _datetime_to_json(row.created_at),
        "updated_at": _datetime_to_json(row.updated_at),
    }


def _parse_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        raise ValueError("Request body is empty")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    if not isinstance(decoded, dict):
        raise ValueError("Request body must be a JSON object")
    return decoded


def _validate_writable_fields(
    name: Any, description: Any, payload: Any
) -> None:
    _validate_name(name)
    _validate_description(description)
    _validate_payload(payload)


def _validate_name(name: Any) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("`name` must be a non-empty string")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"`name` must be {MAX_NAME_LENGTH} characters or fewer")


def _validate_description(description: Any) -> None:
    if description is None:
        return
    if not isinstance(description, str):
        raise ValueError("`description` must be a string or null")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            f"`description` must be {MAX_DESCRIPTION_LENGTH} characters or fewer"
        )


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("`payload` must be a JSON object")
    encoded_size = len(json.dumps(payload).encode("utf-8"))
    if encoded_size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"`payload` must be {MAX_PAYLOAD_BYTES} bytes or fewer "
            f"when JSON-encoded; got {encoded_size}"
        )


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validation_error(message: str) -> Response:
    return _json_response(
        {"status": "error", "message": message},
        status=400,
    )


def _auth_error() -> Response:
    return _json_response(
        {"status": "error", "message": "Could not identify caller."},
        status=401,
    )


def _not_found() -> Response:
    return _json_response(
        {"status": "error", "message": "Test case not found."},
        status=404,
    )


def _json_response(body: dict[str, Any], status: int = 200) -> Response:
    return Response(
        json.dumps(body).encode("utf-8"),
        status=status,
        mimetype="application/json",
    )
