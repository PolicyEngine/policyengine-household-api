#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


LAUNCH_STAGE_ANNOTATION = "run.googleapis.com/launch-stage"
SCALING_CONCURRENCY_TARGET_ANNOTATION = (
    "run.googleapis.com/scaling-concurrency-target"
)


def main() -> int:
    args = _parse_args()
    service = yaml.safe_load(args.input_yaml.read_text())
    apply_scaling_controls(
        service,
        scaling_concurrency_target=args.scaling_concurrency_target,
    )
    args.output_yaml.write_text(
        yaml.safe_dump(service, sort_keys=False),
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Cloud Run scaling-control annotations to YAML.",
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
        "--scaling-concurrency-target",
        required=True,
        help="Cloud Run scaling concurrency target, such as 0.3.",
    )
    args = parser.parse_args()
    _validate_fraction(
        args.scaling_concurrency_target,
        "--scaling-concurrency-target",
    )
    return args


def _validate_fraction(raw_value: str, option_name: str) -> None:
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise SystemExit(f"{option_name} must be a number") from exc
    if value <= 0 or value > 1:
        raise SystemExit(f"{option_name} must be greater than 0 and at most 1")


def apply_scaling_controls(
    service: dict[str, Any],
    *,
    scaling_concurrency_target: str,
) -> None:
    metadata_annotations = _annotations(service.setdefault("metadata", {}))
    metadata_annotations[LAUNCH_STAGE_ANNOTATION] = "BETA"

    template = service.setdefault("spec", {}).setdefault("template", {})
    template_annotations = _annotations(template.setdefault("metadata", {}))
    template_annotations[SCALING_CONCURRENCY_TARGET_ANNOTATION] = (
        scaling_concurrency_target
    )


def _annotations(metadata: dict[str, Any]) -> dict[str, str]:
    annotations = metadata.setdefault("annotations", {})
    if not isinstance(annotations, dict):
        raise SystemExit("metadata.annotations must be a mapping")
    return annotations


if __name__ == "__main__":
    raise SystemExit(main())
