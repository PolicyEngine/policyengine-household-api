#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import sys
import time
from typing import Any
from urllib import error, request

from policyengine_household_api.models.household import HouseholdModelUS
from tests.data.customer_households import my_friend_ben_household


BASE_URL_ENV_VAR = "HOUSEHOLD_API_BASE_URL"
AUTH_TOKEN_ENV_VAR = "HOUSEHOLD_API_AUTH_TOKEN"
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_MAX_ELAPSED_SECONDS = 90.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_RETRY_DELAY_SECONDS = 10.0


@dataclass(frozen=True)
class WarmAttempt:
    attempt: int
    status_code: int | None
    elapsed_seconds: float
    backend: str | None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status_code == 200 and self.error is None


def main() -> int:
    args = _parse_args()
    package_version = _resolve_package_version(args.base_url, args.channel)
    payload = _mfb_payload(args.channel)

    print(
        "Prewarming Cloud Run gateway for "
        f"{args.channel} ({package_version}) with my_friend_ben"
    )

    attempts: list[WarmAttempt] = []
    for attempt_number in range(1, args.max_attempts + 1):
        attempt = _post_calculation(
            attempt=attempt_number,
            base_url=args.base_url,
            payload=payload,
            auth_token=args.auth_token,
            timeout_seconds=args.request_timeout_seconds,
        )
        attempts.append(attempt)
        _print_attempt(attempt)

        if _attempt_is_warm(attempt, args.max_elapsed_seconds):
            print(
                "Cloud Run gateway prewarm succeeded: "
                f"attempt={attempt.attempt} "
                f"elapsed={attempt.elapsed_seconds:.3f}s "
                f"backend={attempt.backend}"
            )
            return 0

        if attempt_number < args.max_attempts:
            time.sleep(args.retry_delay_seconds)

    _print_failure(attempts, args.max_elapsed_seconds)
    return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prewarm a Cloud Run gateway-backed Modal worker by running the "
            "my_friend_ben calculate request until it succeeds under the "
            "gateway latency threshold."
        )
    )
    parser.add_argument(
        "channel",
        choices=("current", "frontier"),
        help="Version channel to prewarm.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv(BASE_URL_ENV_VAR, ""),
        help=f"Gateway base URL. Defaults to ${BASE_URL_ENV_VAR}.",
    )
    parser.add_argument(
        "--auth-token",
        default=os.getenv(AUTH_TOKEN_ENV_VAR, ""),
        help=f"Bearer token. Defaults to ${AUTH_TOKEN_ENV_VAR}.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Maximum warm attempts. Defaults to {DEFAULT_MAX_ATTEMPTS}.",
    )
    parser.add_argument(
        "--max-elapsed-seconds",
        type=float,
        default=DEFAULT_MAX_ELAPSED_SECONDS,
        help=(
            "Maximum acceptable successful response time. Defaults to "
            f"{DEFAULT_MAX_ELAPSED_SECONDS:g}."
        ),
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        help=(
            "Per-attempt client timeout. Defaults to "
            f"{DEFAULT_REQUEST_TIMEOUT_SECONDS:g}."
        ),
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=DEFAULT_RETRY_DELAY_SECONDS,
        help=(
            "Delay between failed attempts. Defaults to "
            f"{DEFAULT_RETRY_DELAY_SECONDS:g}."
        ),
    )
    args = parser.parse_args()

    if not args.base_url:
        parser.error(f"--base-url or ${BASE_URL_ENV_VAR} is required")
    if not args.auth_token:
        parser.error(f"--auth-token or ${AUTH_TOKEN_ENV_VAR} is required")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    if args.max_elapsed_seconds <= 0:
        parser.error("--max-elapsed-seconds must be greater than 0")
    if args.request_timeout_seconds <= 0:
        parser.error("--request-timeout-seconds must be greater than 0")
    if args.retry_delay_seconds < 0:
        parser.error("--retry-delay-seconds must be non-negative")
    return args


def _resolve_package_version(base_url: str, channel: str) -> str:
    url = f"{base_url.rstrip('/')}/versions/us"
    try:
        with request.urlopen(url, timeout=30) as response:
            versions = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise SystemExit(
            f"Could not load active Cloud Run channels: HTTP {exc.code}"
        ) from exc
    except (OSError, TimeoutError) as exc:
        raise SystemExit(
            f"Could not load active Cloud Run channels: {exc}"
        ) from exc

    package_version = versions.get(channel)
    if not package_version:
        raise SystemExit(
            f"Cloud Run gateway does not expose `{channel}` for US"
        )
    return package_version


def _mfb_payload(channel: str) -> dict[str, Any]:
    household = HouseholdModelUS(**my_friend_ben_household)
    return {
        "version": channel,
        "household": household.model_dump(),
    }


def _post_calculation(
    *,
    attempt: int,
    base_url: str,
    payload: dict[str, Any],
    auth_token: str,
    timeout_seconds: float,
) -> WarmAttempt:
    url = f"{base_url.rstrip('/')}/us/calculate"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started_at = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            elapsed_seconds = time.perf_counter() - started_at
            return WarmAttempt(
                attempt=attempt,
                status_code=response.status,
                elapsed_seconds=elapsed_seconds,
                backend=_header(response.headers, "X-PolicyEngine-Backend"),
                error=_response_error(response.status, text),
            )
    except error.HTTPError as exc:
        exc.read()
        return WarmAttempt(
            attempt=attempt,
            status_code=exc.code,
            elapsed_seconds=time.perf_counter() - started_at,
            backend=_header(exc.headers, "X-PolicyEngine-Backend"),
            error=f"HTTP {exc.code}",
        )
    except (OSError, TimeoutError) as exc:
        return WarmAttempt(
            attempt=attempt,
            status_code=None,
            elapsed_seconds=time.perf_counter() - started_at,
            backend=None,
            error=str(exc),
        )


def _header(headers: Any, name: str) -> str | None:
    return headers.get(name) or headers.get(name.lower())


def _response_error(status_code: int, text: str) -> str | None:
    if status_code != 200:
        return f"HTTP {status_code}"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "response was not JSON"
    if payload.get("status") != "ok":
        return f"response status was {payload.get('status')!r}"
    if not payload.get("result"):
        return "response result was empty"
    return None


def _attempt_is_warm(
    attempt: WarmAttempt,
    max_elapsed_seconds: float,
) -> bool:
    return (
        attempt.succeeded
        and attempt.backend == "modal"
        and attempt.elapsed_seconds < max_elapsed_seconds
    )


def _print_attempt(attempt: WarmAttempt) -> None:
    status_code = attempt.status_code or "network_error"
    print(
        "attempt={attempt} status={status} elapsed={elapsed:.3f}s "
        "backend={backend} error={error}".format(
            attempt=attempt.attempt,
            status=status_code,
            elapsed=attempt.elapsed_seconds,
            backend=attempt.backend or "none",
            error=attempt.error or "none",
        )
    )


def _print_failure(
    attempts: list[WarmAttempt],
    max_elapsed_seconds: float,
) -> None:
    last_attempt = attempts[-1]
    print(
        "Cloud Run gateway prewarm failed: "
        f"attempts={len(attempts)} "
        f"max_elapsed_seconds={max_elapsed_seconds:g} "
        f"last_status={last_attempt.status_code or 'network_error'} "
        f"last_elapsed={last_attempt.elapsed_seconds:.3f}s "
        f"last_backend={last_attempt.backend or 'none'} "
        f"last_error={last_attempt.error or 'none'}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
