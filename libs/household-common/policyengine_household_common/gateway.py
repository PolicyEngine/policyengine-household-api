from __future__ import annotations

import json
from typing import Any, Protocol

from flask import Response, jsonify, request

from policyengine_household_common.constants import COUNTRIES
from policyengine_observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    current_context,
    traceparent_header,
)
from policyengine_household_common.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
    modal_routing_payload,
)
from policyengine_household_common.version_routing import VersionRoutingError


VERSIONED_ENDPOINTS = {"calculate", "calculate_demo"}


class ResolvedRequest(Protocol):
    requested_version: str
    channel: str


class GatewayResolutionError(VersionRoutingError):
    pass


def _extract_requested_version(body: bytes) -> tuple[bytes, str]:
    if not body:
        return body, "current"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body, "current"

    if not isinstance(payload, dict):
        return body, "current"

    requested_version = payload.pop("version", "current") or "current"
    if not isinstance(requested_version, str):
        raise GatewayResolutionError("`version` must be a string")

    return json.dumps(payload).encode("utf-8"), requested_version


def _country_and_endpoint(path: str) -> tuple[str | None, str | None]:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] not in COUNTRIES:
        return None, None
    return parts[0], parts[1]


def _request_payload(
    path: str,
    body: bytes,
    resolved_app: ResolvedRequest,
) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": path,
        "query_string": request.query_string.decode("utf-8"),
        "headers": _forward_headers(),
        "body": body,
        MODAL_ROUTING_PAYLOAD_KEY: modal_routing_payload(
            requested_version=resolved_app.requested_version,
            resolved_channel=resolved_app.channel,
        ),
    }


def _forward_headers() -> dict[str, str]:
    forwarded_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    if request.content_type:
        forwarded_headers["Content-Type"] = request.content_type
    context = current_context()
    if context is not None:
        forwarded_headers[REQUEST_ID_HEADER] = context.request_id
        forwarded_headers[OBSERVABILITY_INTERNAL_DISPATCH_HEADER] = "1"
    traceparent = traceparent_header()
    if traceparent:
        forwarded_headers[TRACEPARENT_HEADER] = traceparent
    return forwarded_headers


def _response_from_dispatch_result(result: dict[str, Any]) -> Response:
    body = result.get("body", b"")
    if isinstance(body, str):
        body = body.encode("utf-8")
    return Response(
        body,
        status=int(result["status_code"]),
        headers=list(result.get("headers") or []),
    )


def _json_error(
    message: str,
    status: int,
    *,
    code: str | None = None,
    requested_version: str | None = None,
    country_id: str | None = None,
    available_versions: dict[str, str] | None = None,
) -> Response:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if code is not None:
        payload["code"] = code
    if requested_version is not None:
        payload["requested_version"] = requested_version
    if country_id is not None:
        payload["country_id"] = country_id
    if available_versions is not None:
        payload["available_versions"] = available_versions
    response = jsonify(payload)
    response.status_code = status
    return response
