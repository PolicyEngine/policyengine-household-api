from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import modal

from policyengine_household_failover.manifest import (
    build_failover_manifest,
)
from policyengine_household_common.release_manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    require_active_current_and_frontier,
)
from policyengine_household_common.version_config import (
    ACTIVE_RELEASE_CHANNELS,
)


def active_failover_channels(
    modal_manifest: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    manifest = require_active_current_and_frontier(modal_manifest)
    channels = []
    for channel in ACTIVE_RELEASE_CHANNELS:
        reference = manifest[channel]
        channels.append(
            {
                "channel": channel,
                "modal_app_name": reference["app_name"],
                "package_versions": dict(reference["package_versions"]),
            }
        )
    return channels


def build_manifest_for_worker_urls(
    *,
    environment: str,
    modal_manifest: Mapping[str, Any] | None,
    worker_urls: Mapping[str, str],
) -> dict[str, Any]:
    manifest = require_active_current_and_frontier(modal_manifest)
    return build_failover_manifest(
        environment=environment,
        modal_manifest=manifest,
        worker_urls=worker_urls,
    )


def parse_worker_urls(values: list[str] | None) -> dict[str, str]:
    worker_urls: dict[str, str] = {}
    for value in values or []:
        channel, separator, url = value.partition("=")
        if separator != "=" or not channel or not url:
            raise ValueError("--worker-url values must use CHANNEL=URL format")
        if channel not in ACTIVE_RELEASE_CHANNELS:
            raise ValueError(f"Unsupported failover channel: {channel}")
        if channel in worker_urls:
            raise ValueError(f"Duplicate worker URL for channel: {channel}")
        worker_urls[channel] = url
    return worker_urls


def load_modal_manifest(modal_environment: str) -> dict[str, Any]:
    manifest_dict = modal.Dict.from_name(
        MANIFEST_DICT_NAME,
        create_if_missing=False,
        environment_name=modal_environment,
    )
    return manifest_dict.get(MANIFEST_DICT_KEY)


def main() -> None:
    args = _parse_args()
    modal_manifest = load_modal_manifest(args.modal_environment)

    if args.output_json or args.output_tsv:
        channels = active_failover_channels(modal_manifest)
        if args.output_json:
            _write_json(args.output_json, channels)
        if args.output_tsv:
            _write_channel_tsv(args.output_tsv, channels)
        print(json.dumps(channels, indent=2, sort_keys=True))

    if args.manifest_output:
        worker_urls = parse_worker_urls(args.worker_url)
        manifest = build_manifest_for_worker_urls(
            environment=args.environment,
            modal_manifest=modal_manifest,
            worker_urls=worker_urls,
        )
        _write_json(args.manifest_output, manifest)
        print(json.dumps(manifest, indent=2, sort_keys=True))


def _write_json(path: str, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_channel_tsv(path: str, channels: list[dict[str, Any]]) -> None:
    lines = [
        "\t".join(
            (
                channel["channel"],
                channel["modal_app_name"],
                json.dumps(
                    channel["package_versions"],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
        for channel in channels
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Cloud Run failover metadata from Modal manifest."
    )
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument("--environment", default="staging")
    parser.add_argument("--output-json")
    parser.add_argument("--output-tsv")
    parser.add_argument("--manifest-output")
    parser.add_argument(
        "--worker-url",
        action="append",
        help="Cloud Run worker URL in CHANNEL=URL form.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
