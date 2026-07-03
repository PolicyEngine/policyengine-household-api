from __future__ import annotations

import base64
from typing import Any

from policyengine_household_common.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
)


BODY_B64_KEY = "body_b64"


def encode_dispatch_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": str(payload.get("method") or "GET"),
        "path": str(payload.get("path") or ""),
        "query_string": str(payload.get("query_string") or ""),
        "headers": dict(payload.get("headers") or {}),
        BODY_B64_KEY: _encode_body(payload.get("body")),
        MODAL_ROUTING_PAYLOAD_KEY: payload.get(MODAL_ROUTING_PAYLOAD_KEY),
    }


def decode_dispatch_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Dispatch request payload must be a JSON object")

    return {
        "method": str(payload.get("method") or "GET"),
        "path": str(payload.get("path") or ""),
        "query_string": str(payload.get("query_string") or ""),
        "headers": dict(payload.get("headers") or {}),
        "body": _decode_body(payload.get(BODY_B64_KEY)),
        MODAL_ROUTING_PAYLOAD_KEY: payload.get(MODAL_ROUTING_PAYLOAD_KEY),
    }


def encode_dispatch_response(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status_code": int(result["status_code"]),
        BODY_B64_KEY: _encode_body(result.get("body")),
        "headers": list(result.get("headers") or []),
    }


def decode_dispatch_response(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Dispatch response payload must be a JSON object")

    return {
        "status_code": int(payload["status_code"]),
        "body": _decode_body(payload.get(BODY_B64_KEY)),
        "headers": [tuple(header) for header in payload.get("headers") or []],
    }


def _encode_body(body: Any) -> str:
    if body is None:
        body_bytes = b""
    elif isinstance(body, bytes):
        body_bytes = body
    elif isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        raise ValueError("Dispatch body must be bytes, string, or None")

    return base64.b64encode(body_bytes).decode("ascii")


def _decode_body(value: Any) -> bytes:
    if value is None:
        return b""
    if not isinstance(value, str):
        raise ValueError("Dispatch body must be base64-encoded text")
    return base64.b64decode(value.encode("ascii"))
