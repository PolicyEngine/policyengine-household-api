#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
import json
import math
import os
import sys
import time
from typing import Any
from urllib import error, request

from pathlib import Path

# The repo root is not on sys.path when this script runs directly (the
# workspace's editable installs point at libs/, not the root), so anchor the
# root explicitly to import the shared test household data.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.data.customer_households import (  # noqa: E402
    my_friend_ben_household,
)


BASE_URL_ENV_VAR = "HOUSEHOLD_API_BASE_URL"
AUTH_TOKEN_ENV_VAR = "HOUSEHOLD_API_AUTH_TOKEN"
REQUEST_VERSION_ENV_VAR = "HOUSEHOLD_API_REQUEST_VERSION"
DEFAULT_CONCURRENCY = 25
DEFAULT_REQUESTS = 100
DEFAULT_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class LoadTestResult:
    status_code: int | None
    elapsed_seconds: float
    backend: str | None
    error: str | None = None


def main() -> int:
    args = _parse_args()
    payload = _load_payload(args.payload_file, args.request_version)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency,
    ) as executor:
        futures = [
            executor.submit(
                _post_calculation,
                args.base_url,
                args.path,
                payload,
                args.auth_token,
                args.timeout_seconds,
            )
            for _ in range(args.requests)
        ]
        results = [future.result() for future in futures]

    return _report_results(
        results,
        expected_backend=args.expected_backend,
        max_error_rate=args.max_error_rate,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load-test a deployed household API Cloud Run gateway with a real "
            "US calculation request."
        )
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
        "--path",
        default="/us/calculate",
        help="Gateway path to POST. Defaults to /us/calculate.",
    )
    parser.add_argument(
        "--request-version",
        default=os.getenv(REQUEST_VERSION_ENV_VAR, ""),
        help=f"Optional request version. Defaults to ${REQUEST_VERSION_ENV_VAR}.",
    )
    parser.add_argument(
        "--payload-file",
        help=(
            "Optional JSON file containing the full request payload. The "
            "default payload uses the my_friend_ben household fixture."
        ),
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"Total requests to send. Defaults to {DEFAULT_REQUESTS}.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Concurrent requests. Defaults to {DEFAULT_CONCURRENCY}.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout. Defaults to {DEFAULT_TIMEOUT_SECONDS}.",
    )
    parser.add_argument(
        "--expected-backend",
        choices=("modal", "cloud_run"),
        help="Require X-PolicyEngine-Backend to match this value.",
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.0,
        help="Allowed non-200 response fraction. Defaults to 0.",
    )
    args = parser.parse_args()

    if not args.base_url:
        parser.error(f"--base-url or ${BASE_URL_ENV_VAR} is required")
    if args.requests < 1:
        parser.error("--requests must be at least 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.max_error_rate < 0 or args.max_error_rate > 1:
        parser.error("--max-error-rate must be between 0 and 1")
    return args


def _load_payload(
    payload_file: str | None,
    request_version: str,
) -> dict[str, Any]:
    if payload_file:
        with open(payload_file) as file:
            return json.load(file)

    payload: dict[str, Any] = {"household": my_friend_ben_household}
    if request_version:
        payload["version"] = request_version
    return payload


def _post_calculation(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    auth_token: str,
    timeout_seconds: float,
) -> LoadTestResult:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    started_at = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response.read()
            return LoadTestResult(
                status_code=response.status,
                elapsed_seconds=time.perf_counter() - started_at,
                backend=response.headers.get("X-PolicyEngine-Backend"),
            )
    except error.HTTPError as exc:
        exc.read()
        return LoadTestResult(
            status_code=exc.code,
            elapsed_seconds=time.perf_counter() - started_at,
            backend=exc.headers.get("X-PolicyEngine-Backend"),
            error=f"HTTP {exc.code}",
        )
    except (OSError, TimeoutError) as exc:
        return LoadTestResult(
            status_code=None,
            elapsed_seconds=time.perf_counter() - started_at,
            backend=None,
            error=str(exc),
        )


def _report_results(
    results: list[LoadTestResult],
    *,
    expected_backend: str | None,
    max_error_rate: float,
) -> int:
    successful = [result for result in results if result.status_code == 200]
    failed = [result for result in results if result.status_code != 200]
    backend_mismatches = [
        result
        for result in successful
        if expected_backend and result.backend != expected_backend
    ]
    elapsed = sorted(result.elapsed_seconds for result in results)
    error_rate = len(failed) / len(results)

    print(
        "requests={requests} success={success} failed={failed} "
        "error_rate={error_rate:.3f} p50={p50:.3f}s p90={p90:.3f}s "
        "p95={p95:.3f}s p99={p99:.3f}s max={max_elapsed:.3f}s".format(
            requests=len(results),
            success=len(successful),
            failed=len(failed),
            error_rate=error_rate,
            p50=_percentile(elapsed, 50),
            p90=_percentile(elapsed, 90),
            p95=_percentile(elapsed, 95),
            p99=_percentile(elapsed, 99),
            max_elapsed=elapsed[-1],
        )
    )

    if expected_backend:
        print(f"expected_backend={expected_backend}")
    print(f"observed_backends={_backend_counts(results)}")
    print(f"status_codes={_status_counts(results)}")

    if failed:
        print(f"sample_error={failed[0].error}", file=sys.stderr)
    if backend_mismatches:
        mismatch = backend_mismatches[0]
        print(
            "backend_mismatch="
            f"expected {expected_backend}, got {mismatch.backend}",
            file=sys.stderr,
        )

    if error_rate > max_error_rate or backend_mismatches:
        return 1
    return 0


def _percentile(values: list[float], percentile: int) -> float:
    index = max(0, math.ceil((percentile / 100) * len(values)) - 1)
    return values[min(index, len(values) - 1)]


def _backend_counts(results: list[LoadTestResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        backend = result.backend or "none"
        counts[backend] = counts.get(backend, 0) + 1
    return counts


def _status_counts(results: list[LoadTestResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        status = str(result.status_code or "network_error")
        counts[status] = counts.get(status, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
