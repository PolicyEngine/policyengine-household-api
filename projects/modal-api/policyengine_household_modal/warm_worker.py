"""Block until a freshly deployed Modal worker version actually serves.

``modal deploy`` returns once the new version is registered, but the worker
only builds its CPU memory snapshot and initialises the API on first
invocation, ~60-90 seconds later. Requests served during that window come
from transitional capacity whose best-effort analytics enqueues can be lost
(issue #1607). The deploy script runs this after each worker deploy so the
deploy job cannot report success until the new version demonstrably serves —
the same principle as the Cloud Run startup probes: a successful deploy
proves nothing; only a served request does.
"""

from __future__ import annotations

import argparse
import json
import time

from policyengine_household_api.constants import VERSION
from policyengine_household_common.worker_dispatch import (
    WorkerRequest,
    call_modal_worker_dispatch,
)

# The first dispatch triggers the worker's snapshot build and API
# initialisation, so the budget must cover a full cold start, not a network
# round trip. Matches the Cloud Run fallback worker warm budget.
DEFAULT_TIMEOUT_SECONDS = 1200
RETRY_BACKOFF_SECONDS = 10

# The raw payload shape the Cloud Run HTTP service sends to
# HouseholdWorker.handle_household_request; see
# policyengine_household_common.gateway.build_worker_request.
LIVENESS_DISPATCH_PAYLOAD: WorkerRequest = {
    "method": "GET",
    "path": "/liveness_check",
    "query_string": "",
    "headers": {},
    "body": b"",
}
SPECIFICATION_DISPATCH_PAYLOAD: WorkerRequest = {
    "method": "GET",
    "path": "/specification",
    "query_string": "",
    "headers": {},
    "body": b"",
}


def _specification_error(result: dict) -> str | None:
    status_code = int(result["status_code"])
    if status_code != 200:
        return f"specification dispatch returned {status_code}"

    try:
        payload = json.loads(result["body"])
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"specification dispatch returned invalid JSON: {exc}"

    if not isinstance(payload, dict):
        return "specification dispatch did not return a JSON object"
    if payload.get("openapi") != "3.0.0":
        return "specification dispatch did not return OpenAPI 3.0.0"

    reported_version = payload.get("info", {}).get("version")
    if reported_version != VERSION:
        return (
            "specification dispatch reported API version "
            f"{reported_version!r}, expected {VERSION!r}"
        )
    return None


def warm_worker_app(
    app_name: str,
    *,
    modal_environment: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> None:
    import modal

    deadline = monotonic() + timeout_seconds
    last_error: str | None = None
    attempt = 0

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        attempt += 1
        try:
            result = call_modal_worker_dispatch(
                app_name,
                LIVENESS_DISPATCH_PAYLOAD,
                environment_name=modal_environment,
                timeout_seconds=remaining,
            )
            status_code = int(result["status_code"])
            if status_code == 200:
                specification_remaining = deadline - monotonic()
                if specification_remaining <= 0:
                    last_error = (
                        "liveness dispatch returned 200 but no time remained "
                        "for specification verification"
                    )
                else:
                    specification_result = call_modal_worker_dispatch(
                        app_name,
                        SPECIFICATION_DISPATCH_PAYLOAD,
                        environment_name=modal_environment,
                        timeout_seconds=specification_remaining,
                    )
                    last_error = _specification_error(specification_result)
                if last_error is None:
                    print(
                        f"Worker app {app_name} serves: liveness and "
                        f"specification dispatches passed on attempt "
                        f"{attempt}.",
                        flush=True,
                    )
                    return
            else:
                last_error = f"liveness dispatch returned {status_code}"
        except modal.exception.NotFoundError as exc:
            # Neither the class-based worker nor the legacy function
            # entrypoint exists; retrying cannot fix a missing app.
            raise SystemExit(
                f"Worker app {app_name} has no dispatch entrypoint in "
                f"Modal environment {modal_environment}: {exc!r}"
            )
        except Exception as exc:
            last_error = repr(exc)
        print(f"Attempt {attempt}: {last_error}.", flush=True)
        if monotonic() + RETRY_BACKOFF_SECONDS >= deadline:
            break
        sleep(RETRY_BACKOFF_SECONDS)

    raise SystemExit(
        f"Worker app {app_name} did not serve within {timeout_seconds}s: "
        f"{last_error}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Invoke a deployed Modal worker until its new version serves."
        )
    )
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    warm_worker_app(
        args.app_name,
        modal_environment=args.modal_environment,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    main()
