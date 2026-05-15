from __future__ import annotations

import argparse
import json
from pathlib import Path

import modal

from policyengine_household_api.modal_release.manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    active_app_deployments,
)


def main() -> None:
    args = _parse_args()
    manifest_dict = modal.Dict.from_name(
        MANIFEST_DICT_NAME,
        create_if_missing=True,
        environment_name=args.modal_environment,
    )
    deployments = active_app_deployments(manifest_dict.get(MANIFEST_DICT_KEY))

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(deployments, indent=2, sort_keys=True) + "\n"
        )
    if args.output_tsv:
        lines = [
            "\t".join(
                (
                    deployment["app_name"],
                    json.dumps(
                        deployment["package_versions"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
            for deployment in deployments
        ]
        Path(args.output_tsv).write_text("\n".join(lines) + "\n")

    print(json.dumps(deployments, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit active Modal worker apps from the release manifest."
    )
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--output-tsv")
    return parser.parse_args()


if __name__ == "__main__":
    main()
