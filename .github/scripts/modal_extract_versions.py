from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_household_common.release_manifest import (
    build_app_name,
    current_package_versions,
)


def main() -> None:
    args = _parse_args()
    package_versions = current_package_versions()
    app_name = build_app_name(package_versions)

    if args.github_output:
        with Path(args.github_output).open("a") as output_file:
            output_file.write(f"worker_app_name={app_name}\n")
            for country, version in package_versions.items():
                output_file.write(f"{country}_version={version}\n")

    print(app_name)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit Modal worker app names from installed package versions."
    )
    parser.add_argument("--github-output")
    return parser.parse_args()


if __name__ == "__main__":
    main()
