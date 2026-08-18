"""Public HTTP-to-worker request and response conversion helpers."""

from __future__ import annotations

import json
from typing import Any, Protocol

from flask import Request, Response, jsonify

from policyengine_household_common.constants import COUNTRIES
from policyengine_observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    current_context,
    traceparent_header,
)
from policyengine_household_common.routing_metadata import (
    modal_routing_payload,
)
from policyengine_household_common.version_routing import VersionRoutingError
from policyengine_household_common.worker_dispatch import (
    WorkerRequest,
    WorkerResult,
)


VERSIONED_ENDPOINTS = {"calculate", "calculate_demo"}


class ResolvedRoute(Protocol):
    """Routing fields required to build a worker request."""

    requested_version: str
    channel: str


class RequestVersionError(VersionRoutingError):
    """Raised when a request contains an invalid version selector."""

    pass


def extract_requested_version(body: bytes) -> tuple[bytes, str]:
    """Remove a string version selector from an object-shaped JSON body."""

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
        raise RequestVersionError("`version` must be a string")

    return json.dumps(payload).encode("utf-8"), requested_version


def country_and_endpoint(path: str) -> tuple[str | None, str | None]:
    """Return a supported country and its endpoint from a request path."""

    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] not in COUNTRIES:
        return None, None
    return parts[0], parts[1]


def build_worker_request(
    http_request: Request,
    *,
    path: str,
    body: bytes,
    route: ResolvedRoute,
) -> WorkerRequest:
    """Convert an explicit Flask request and resolved route for dispatch."""

    return {
        "method": http_request.method,
        "path": path,
        "query_string": http_request.query_string.decode("utf-8"),
        "headers": forward_request_headers(http_request),
        "body": body,
        "modal_routing": modal_routing_payload(
            requested_version=route.requested_version,
            resolved_channel=route.channel,
        ),
    }


def forward_request_headers(http_request: Request) -> dict[str, str]:
    """Return safe request headers with internal observability context."""

    forwarded_headers = {
        key: value
        for key, value in http_request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    if http_request.content_type:
        forwarded_headers["Content-Type"] = http_request.content_type
    context = current_context()
    if context is not None:
        forwarded_headers[REQUEST_ID_HEADER] = context.request_id
        forwarded_headers[OBSERVABILITY_INTERNAL_DISPATCH_HEADER] = "1"
    traceparent = traceparent_header()
    if traceparent:
        forwarded_headers[TRACEPARENT_HEADER] = traceparent
    return forwarded_headers


def response_from_worker_result(result: WorkerResult) -> Response:
    """Convert a worker result into a Flask response."""

    body = result.get("body", b"")
    if isinstance(body, str):
        body = body.encode("utf-8")
    return Response(
        body,
        status=int(result["status_code"]),
        headers=list(result.get("headers") or []),
    )


def json_error_response(
    message: str,
    status: int,
    *,
    code: str | None = None,
    requested_version: str | None = None,
    country_id: str | None = None,
    available_versions: dict[str, str] | None = None,
) -> Response:
    """Build the standard JSON error response returned by request routers."""

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
