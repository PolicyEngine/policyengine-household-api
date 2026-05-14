from __future__ import annotations

import sys

from modal_release_check_common import (
    event_pr_body,
    get_changed_files,
    parse_pr_body_check_args,
)
from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfigError,
    body_contains_modal_release_config,
    changed_files_require_modal_release_config,
    parse_modal_release_config_from_body,
)


def main() -> int:
    args = parse_pr_body_check_args(
        "Validate Modal release configuration in a PR body."
    )
    body = event_pr_body(args.event_path)
    changed_files = get_changed_files(args.base_ref)

    try:
        validate_release_body_config(body, changed_files)
    except ModalReleaseConfigError as e:
        print(f"::error::{e}")
        return 1

    print("Modal release body configuration is valid.")
    return 0


def validate_release_body_config(
    body: str | None,
    changed_files: list[str],
) -> None:
    requires_config = changed_files_require_modal_release_config(changed_files)
    has_config = body_contains_modal_release_config(body)

    if not requires_config and not has_config:
        print("No Modal release files changed; config block is optional.")
        return

    if requires_config and not has_config:
        raise ModalReleaseConfigError(
            "This PR changes Modal release files and must include a "
            "`modal_release` YAML block in the PR body"
        )

    parse_modal_release_config_from_body(body)


if __name__ == "__main__":
    sys.exit(main())
