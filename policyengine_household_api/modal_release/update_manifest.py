from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import modal

from policyengine_household_api.modal_release.manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    apply_release_config,
    build_app_reference,
    cleanup_app_names_for_target,
    normalize_manifest,
)
from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfig,
)


def main() -> None:
    args = _parse_args()
    config = ModalReleaseConfig.from_mapping(json.loads(args.config_json))

    manifest_dict = modal.Dict.from_name(
        MANIFEST_DICT_NAME,
        create_if_missing=True,
        environment_name=args.modal_environment,
    )
    current_manifest = normalize_manifest(manifest_dict.get(MANIFEST_DICT_KEY))

    new_app = None
    if config.deploys_new_app:
        new_app = build_app_reference(
            app_name=args.new_app_name,
            source_commit=args.source_commit,
        )

    updated_manifest = apply_release_config(
        current_manifest,
        config,
        new_app=new_app,
    )
    cleanup_app_names = cleanup_app_names_for_target(
        updated_manifest,
        config.cleanup_target,
    )

    manifest_dict[MANIFEST_DICT_KEY] = updated_manifest

    if args.cleanup_output:
        _write_json(
            Path(args.cleanup_output),
            {"app_names": cleanup_app_names},
        )
    if args.manifest_output:
        _write_json(Path(args.manifest_output), updated_manifest)

    print(json.dumps(updated_manifest, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the household API Modal release manifest."
    )
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--new-app-name")
    parser.add_argument("--source-commit")
    parser.add_argument("--modal-environment")
    parser.add_argument("--cleanup-output")
    parser.add_argument("--manifest-output")
    args = parser.parse_args()

    config = ModalReleaseConfig.from_mapping(json.loads(args.config_json))
    if config.deploys_new_app and not args.new_app_name:
        parser.error("--new-app-name is required when deploying a new app")
    return args


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
