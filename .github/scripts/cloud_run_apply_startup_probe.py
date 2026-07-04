#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def main() -> int:
    args = _parse_args()
    service = yaml.safe_load(args.input_yaml.read_text())
    apply_startup_probe(
        service,
        path=args.path,
        period_seconds=args.period_seconds,
        timeout_seconds=args.timeout_seconds,
        failure_threshold=args.failure_threshold,
        initial_delay_seconds=args.initial_delay_seconds,
    )
    args.output_yaml.write_text(
        yaml.safe_dump(service, sort_keys=False),
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply an HTTP startup probe to Cloud Run service YAML.",
    )
    parser.add_argument(
        "--input-yaml",
        type=Path,
        required=True,
        help="Cloud Run service YAML exported with `gcloud run services describe --format export`.",
    )
    parser.add_argument(
        "--output-yaml",
        type=Path,
        required=True,
        help="Path to write the patched Cloud Run service YAML.",
    )
    parser.add_argument(
        "--path",
        default="/liveness_check",
        help="HTTP path the startup probe requests.",
    )
    parser.add_argument(
        "--period-seconds",
        type=int,
        required=True,
        help="Seconds between startup probe attempts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        required=True,
        help="Seconds before a single probe attempt times out.",
    )
    parser.add_argument(
        "--failure-threshold",
        type=int,
        required=True,
        help="Consecutive probe failures before the revision is marked failed.",
    )
    parser.add_argument(
        "--initial-delay-seconds",
        type=int,
        default=0,
        help="Seconds to wait before the first probe attempt.",
    )
    args = parser.parse_args()
    for option_name, value in (
        ("--period-seconds", args.period_seconds),
        ("--timeout-seconds", args.timeout_seconds),
        ("--failure-threshold", args.failure_threshold),
    ):
        if value <= 0:
            raise SystemExit(f"{option_name} must be a positive integer")
    if args.initial_delay_seconds < 0:
        raise SystemExit("--initial-delay-seconds must not be negative")
    return args


def apply_startup_probe(
    service: dict[str, Any],
    *,
    path: str,
    period_seconds: int,
    timeout_seconds: int,
    failure_threshold: int,
    initial_delay_seconds: int = 0,
) -> None:
    containers = (
        service.setdefault("spec", {})
        .setdefault("template", {})
        .setdefault("spec", {})
        .setdefault("containers", [{}])
    )
    if not isinstance(containers, list) or not containers:
        raise SystemExit(
            "spec.template.spec.containers must be a non-empty list"
        )
    containers[0]["startupProbe"] = {
        "httpGet": {"path": path},
        "initialDelaySeconds": initial_delay_seconds,
        "periodSeconds": period_seconds,
        "timeoutSeconds": timeout_seconds,
        "failureThreshold": failure_threshold,
    }


if __name__ == "__main__":
    raise SystemExit(main())
