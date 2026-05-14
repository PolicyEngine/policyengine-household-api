"""
Per-partner saved test-case storage.

Each partner client_id owns a library of household payloads. CRUD is
scoped to the caller's authenticated client_id. PolicyEngine-staff
tokens (those carrying the ``policyengine-staff`` scope) can act on
any partner's behalf via the ``as_client_id`` query parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any

import jwt
from flask import Response, request

from policyengine_household_api.data.analytics_setup import (
    db,
    is_analytics_enabled,
    is_analytics_schema_ready,
)
from policyengine_household_api.data.models import TestCase, TestCaseAudit
from policyengine_household_api.decorators.analytics import (
    _get_jwks_client,
)
from policyengine_household_api.decorators.auth import STAFF_SCOPE
from policyengine_household_api.utils.config_loader import get_config_value


logger = logging.getLogger(__name__)


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

    target = _resolve_target_client_id()
    if target.error is not None:
        return target.error

    rows = (
        db.session.query(TestCase)
        .filter(TestCase.client_id == target.client_id)
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

    target = _resolve_target_client_id()
    if target.error is not None:
        return target.error
    client_id = target.client_id
    actor_client_id = target.actor_client_id

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

    target = _resolve_target_client_id()
    if target.error is not None:
        return target.error
    client_id = target.client_id
    actor_client_id = target.actor_client_id

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
        actor_client_id=actor_client_id,
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

    target = _resolve_target_client_id()
    if target.error is not None:
        return target.error
    client_id = target.client_id
    actor_client_id = target.actor_client_id

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
        actor_client_id=actor_client_id,
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

    target = _resolve_target_client_id()
    if target.error is not None:
        return target.error
    client_id = target.client_id
    actor_client_id = target.actor_client_id

    row = db.session.get(TestCase, test_case_id)
    if row is None or row.client_id != client_id:
        return _not_found()

    name_snapshot = row.name
    db.session.delete(row)
    _record_audit(
        test_case_id=test_case_id,
        client_id=client_id,
        actor_client_id=actor_client_id,
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


@dataclass(frozen=True)
class _ResolvedTarget:
    """Result of resolving who a request is operating *as*.

    ``client_id`` is the partner whose data the request reads or writes.
    ``actor_client_id`` is the authenticated caller — the same as
    ``client_id`` for partner self-service, different when staff act on
    a partner's behalf via ``?as_client_id=…``. ``error`` is set when
    the caller can't be authenticated or the staff override is invalid.
    """

    client_id: str
    actor_client_id: str
    error: Response | None


def _resolve_target_client_id() -> _ResolvedTarget:
    claims = _verified_token_claims(_bearer_token_from_header())
    if claims is None:
        return _ResolvedTarget("", "", _auth_error())

    sub = claims.get("sub")
    if not isinstance(sub, str):
        return _ResolvedTarget("", "", _auth_error())
    actor = _strip_clients_suffix(sub)

    requested = request.args.get("as_client_id")
    if not requested:
        return _ResolvedTarget(
            client_id=actor, actor_client_id=actor, error=None
        )

    if not _has_scope(claims, STAFF_SCOPE):
        return _ResolvedTarget(
            "",
            "",
            _json_response(
                {
                    "status": "error",
                    "message": (
                        "`as_client_id` requires the policyengine-staff scope."
                    ),
                },
                status=403,
            ),
        )

    return _ResolvedTarget(
        client_id=requested, actor_client_id=actor, error=None
    )


def _bearer_token_from_header() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _verified_token_claims(token: str | None) -> dict[str, Any] | None:
    """Decode the bearer token against the configured Auth0 JWKS and
    return its full claims dict on success. Mirrors the verification
    discipline used by ``decorators.analytics._verified_sub_claim`` —
    if Auth0 isn't configured the token can't be trusted and we return
    ``None`` so the caller falls back to the auth-error path.
    """
    if not token:
        return None
    auth0_address = get_config_value("auth.auth0.address", "")
    auth0_audience = get_config_value("auth.auth0.audience", "")
    if not auth0_address or not auth0_audience:
        return None
    try:
        signing_key = _get_jwks_client(auth0_address).get_signing_key_from_jwt(
            token
        )
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=auth0_audience,
            issuer=f"https://{auth0_address}/",
            options={"verify_signature": True},
        )
    except Exception as e:
        logger.debug(f"JWT signature verification failed: {e}")
        return None
    return claims


def _strip_clients_suffix(sub: str) -> str:
    suffix = "@clients"
    return sub[: -len(suffix)] if sub.endswith(suffix) else sub


def _has_scope(claims: dict[str, Any], scope: str) -> bool:
    """Return True if the JWT carries the named scope. Auth0 issues
    scopes as a space-separated string in the ``scope`` claim and (on
    M2M tokens) sometimes as a list under ``scopes``."""
    scope_value = claims.get("scope")
    if isinstance(scope_value, str):
        return scope in scope_value.split()
    scopes_value = claims.get("scopes")
    if isinstance(scopes_value, (list, tuple)):
        return scope in scopes_value
    return False


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
