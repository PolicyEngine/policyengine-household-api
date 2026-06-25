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
    prune_cleaned_retired_apps,
    validate_manifest,
)
from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfig,
)


def main() -> None:
    args = _parse_args()
    config = ModalReleaseConfig.from_mapping(
        json.loads(args.config_json),
        allow_active_cleanup=True,
    )

    manifest_dict = modal.Dict.from_name(
        MANIFEST_DICT_NAME,
        create_if_missing=True,
        environment_name=args.modal_environment,
    )
    current_manifest = validate_manifest(manifest_dict.get(MANIFEST_DICT_KEY))

    new_app = None
    if config.deploys_new_app:
        new_app = build_app_reference(
            app_name=args.new_app_name,
            analytics_database_revision=args.analytics_database_revision,
        )

    updated_manifest = apply_release_config(
        current_manifest,
        config,
        new_app=new_app,
    )
    cleanup_app_names = cleanup_app_names_for_target(
        updated_manifest,
        config.cleanup_target,
        previous_manifest=current_manifest,
    )

    # Drop the apps scheduled for cleanup from the manifest's retired history so
    # they are not re-listed for cleanup on every future release. The deferred
    # cleanup still receives the full list via `cleanup_app_names` (written to
    # the cleanup output before this prune); only the stored manifest shrinks.
    # The actual `modal app stop` happens later in the same release run and is
    # idempotent, so pruning here does not strand an app. Without this, a
    # long-since-deleted app lingers in `retired` forever and every release
    # keeps trying to stop it. See issue #1569.
    updated_manifest = prune_cleaned_retired_apps(
        updated_manifest, set(cleanup_app_names)
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
    parser.add_argument("--analytics-database-revision")
    parser.add_argument("--modal-environment")
    parser.add_argument("--cleanup-output")
    parser.add_argument("--manifest-output")
    args = parser.parse_args()

    config = ModalReleaseConfig.from_mapping(
        json.loads(args.config_json),
        allow_active_cleanup=True,
    )
    if config.deploys_new_app and not args.new_app_name:
        parser.error("--new-app-name is required when deploying a new app")
    return args


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
