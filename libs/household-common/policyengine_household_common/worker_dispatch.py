from __future__ import annotations

from typing import Any

from policyengine_household_common.observability.segments import SegmentName
from policyengine_household_common.routing_metadata import (
    routing_environ_overrides,
)
from policyengine_observability import segment


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
    environ_overrides = routing_environ_overrides(payload)

    response = flask_app.test_client().open(
        path=path,
        method=method,
        data=body if method != "GET" else None,
        headers=headers,
        environ_overrides=environ_overrides,
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


def call_modal_worker_dispatch(
    app_name: str,
    payload: dict[str, Any],
    *,
    environment_name: str | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Dispatch a request payload to a deployed Modal worker app.

    Prefer the class-based worker (post #1528). During a release transition
    the existing frontier is promoted to current without a redeploy, so for
    one release cycle the current worker may still expose the pre-#1528
    top-level ``handle_household_request`` function; fall back to that shape
    when the class is not present.

    ``timeout_seconds`` bounds the wait for the dispatch result; without it
    Modal waits indefinitely, including for an input queued behind a
    container that never finishes booting.
    """
    import modal

    lookup_kwargs: dict[str, Any] = {}
    if environment_name:
        lookup_kwargs["environment_name"] = environment_name

    try:
        with segment(SegmentName.MODAL_WORKER_LOOKUP, backend="modal"):
            worker_cls = modal.Cls.from_name(
                app_name,
                "HouseholdWorker",
                **lookup_kwargs,
            )
        with segment(SegmentName.MODAL_REMOTE_EXECUTION, backend="modal"):
            return _dispatch_result(
                worker_cls().handle_household_request,
                payload,
                timeout_seconds,
            )
    except modal.exception.NotFoundError:
        with segment(SegmentName.MODAL_WORKER_LOOKUP, backend="modal"):
            worker_function = modal.Function.from_name(
                app_name,
                "handle_household_request",
                **lookup_kwargs,
            )
        with segment(SegmentName.MODAL_REMOTE_EXECUTION, backend="modal"):
            return _dispatch_result(
                worker_function,
                payload,
                timeout_seconds,
            )


def _dispatch_result(
    method: Any,
    payload: dict[str, Any],
    timeout_seconds: float | None,
) -> dict[str, Any]:
    if timeout_seconds is None:
        return method.remote(payload)
    return method.spawn(payload).get(timeout=timeout_seconds)
