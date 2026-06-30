from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import modal
from modal.exception import NotFoundError

from policyengine_household_api.modal_release.manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    prune_cleaned_retired_apps,
    require_active_current_and_frontier,
)


def main() -> int:
    args = _parse_args()

    cleanup_payload = json.loads(Path(args.cleanup_json).read_text())
    app_names = {
        app_name
        for app_name in cleanup_payload.get("app_names", [])
        if app_name
    }
    if not app_names:
        print("No cleaned-up apps to prune from the release manifest.")
        return 0

    try:
        manifest_dict = modal.Dict.from_name(
            MANIFEST_DICT_NAME,
            create_if_missing=False,
            environment_name=args.modal_environment,
        )
    except NotFoundError:
        print(
            "Modal release manifest is missing; refusing to prune retired "
            "history.",
            file=sys.stderr,
        )
        return 1

    try:
        current_manifest = require_active_current_and_frontier(
            manifest_dict.get(MANIFEST_DICT_KEY)
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    retired_before = _retired_app_names(current_manifest)

    pruned_manifest = prune_cleaned_retired_apps(current_manifest, app_names)
    manifest_dict[MANIFEST_DICT_KEY] = pruned_manifest

    pruned = sorted(app_names & retired_before)
    print(
        f"Pruned {len(pruned)} cleaned-up app(s) from the release manifest's "
        f"retired history: {', '.join(pruned) if pruned else '(none matched)'}"
    )
    return 0


def _retired_app_names(manifest: dict) -> set[str]:
    return {
        app["app_name"]
        for app in manifest.get("retired", [])
        if isinstance(app, dict) and app.get("app_name")
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prune already-cleaned-up retired apps from the household API "
            "Modal release manifest."
        )
    )
    parser.add_argument("--cleanup-json", required=True)
    parser.add_argument("--modal-environment", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
