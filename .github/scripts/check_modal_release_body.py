from __future__ import annotations

import sys
from pathlib import Path

from modal_release_check_common import (
    event_pr_body,
    get_changed_files,
    get_file_at_ref,
    parse_pr_body_check_args,
)
from policyengine_household_common.release_config import (
    ModalReleaseConfigError,
    body_contains_modal_release_config,
    parse_modal_release_config_from_body,
    release_package_versions_changed,
)


def main() -> int:
    args = parse_pr_body_check_args(
        "Validate Modal release configuration in a PR body."
    )
    body = event_pr_body(args.event_path)
    changed_files = get_changed_files(args.base_ref)
    package_versions_changed = changed_files_update_release_packages(
        changed_files,
        args.base_ref,
    )

    try:
        validate_release_body_config(body, package_versions_changed)
    except ModalReleaseConfigError as e:
        print(f"::error::{e}")
        return 1

    print("Modal release body configuration is valid.")
    return 0


def validate_release_body_config(
    body: str | None,
    package_versions_changed: bool,
) -> None:
    has_config = body_contains_modal_release_config(body)

    if not package_versions_changed and not has_config:
        print("No US or UK package version changed; config block is optional.")
        return

    if package_versions_changed and not has_config:
        raise ModalReleaseConfigError(
            "This PR changes a US or UK package version and must include "
            "a `modal_release` YAML block in the PR body"
        )

    parse_modal_release_config_from_body(body)


def changed_files_update_release_packages(
    changed_files: list[str],
    base_ref: str | None,
) -> bool:
    if "pyproject.toml" not in changed_files:
        return False

    return release_package_versions_changed(
        get_file_at_ref("pyproject.toml", base_ref),
        Path("pyproject.toml").read_text(encoding="utf-8"),
    )


if __name__ == "__main__":
    sys.exit(main())
