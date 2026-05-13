from __future__ import annotations

from typing import Any


HOP_BY_HOP_RESPONSE_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "transfer-encoding",
}


def dispatch_to_flask_app(
    flask_app, payload: dict[str, Any]
) -> dict[str, Any]:
    path = _path_with_query(
        str(payload.get("path") or ""),
        str(payload.get("query_string") or ""),
    )
    method = str(payload.get("method") or "GET")
    body = payload.get("body")
    headers = dict(payload.get("headers") or {})

    response = flask_app.test_client().open(
        path=path,
        method=method,
        data=body if method != "GET" else None,
        headers=headers,
    )

    return {
        "status_code": response.status_code,
        "body": response.get_data(),
        "headers": [
            (key, value)
            for key, value in response.headers.items()
            if key.lower() not in HOP_BY_HOP_RESPONSE_HEADERS
        ],
    }


def _path_with_query(path: str, query_string: str) -> str:
    normalized_path = "/" + path.lstrip("/")
    if query_string:
        return f"{normalized_path}?{query_string}"
    return normalized_path
