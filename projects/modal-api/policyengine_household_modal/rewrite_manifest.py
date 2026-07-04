from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import modal

from policyengine_household_common.release_manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    rewrite_existing_manifest_for_storage,
)


def main() -> None:
    args = _parse_args()
    manifest_dict = modal.Dict.from_name(
        MANIFEST_DICT_NAME,
        create_if_missing=False,
        environment_name=args.modal_environment,
    )
    rewritten_manifest = rewrite_modal_manifest(manifest_dict)

    if args.manifest_output:
        _write_json(Path(args.manifest_output), rewritten_manifest)

    print(json.dumps(rewritten_manifest, indent=2, sort_keys=True))


def rewrite_modal_manifest(manifest_dict) -> dict[str, Any]:
    rewritten_manifest = rewrite_existing_manifest_for_storage(
        manifest_dict.get(MANIFEST_DICT_KEY)
    )
    manifest_dict[MANIFEST_DICT_KEY] = rewritten_manifest
    return rewritten_manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite the household API Modal release manifest."
    )
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument("--manifest-output")
    return parser.parse_args()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
