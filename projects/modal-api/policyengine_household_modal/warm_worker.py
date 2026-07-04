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
import sys
import time

from policyengine_household_common.dispatch_codec import (
    decode_dispatch_response,
    encode_dispatch_request,
)

DEFAULT_TIMEOUT_SECONDS = 600
RETRY_BACKOFF_SECONDS = 10


def _liveness_dispatch_payload() -> dict:
    return encode_dispatch_request(
        {
            "method": "GET",
            "path": "liveness_check",
            "query_string": "",
            "headers": {},
            "body": None,
        }
    )


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
    payload = _liveness_dispatch_payload()
    last_error: str | None = None
    attempt = 0

    while monotonic() < deadline:
        attempt += 1
        try:
            worker_cls = modal.Cls.from_name(
                app_name,
                "HouseholdWorker",
                environment_name=modal_environment,
            )
            raw = worker_cls().handle_household_request.remote(payload)
            response = decode_dispatch_response(raw)
            status_code = int(response.get("status_code") or 0)
            if status_code == 200:
                print(
                    f"Worker app {app_name} serves (attempt {attempt}, "
                    "liveness dispatch returned 200)."
                )
                return
            last_error = f"liveness dispatch returned {status_code}"
        except Exception as exc:  # noqa: BLE001 - report and retry
            last_error = repr(exc)
        sleep(RETRY_BACKOFF_SECONDS)

    raise SystemExit(
        f"Worker app {app_name} did not serve within {timeout_seconds}s: "
        f"{last_error}"
    )


def main() -> int:
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

    warm_worker_app(
        args.app_name,
        modal_environment=args.modal_environment,
        timeout_seconds=args.timeout_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
