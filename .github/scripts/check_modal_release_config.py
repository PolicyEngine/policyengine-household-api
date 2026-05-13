from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from policyengine_household_api.modal_release.release_config import (
    CONFIG_KEY,
    ModalReleaseConfigError,
    changed_files_require_modal_release_config,
    parse_modal_release_config_from_body,
)


def main() -> int:
    args = _parse_args()
    event = json.loads(Path(args.event_path).read_text())
    body = (event.get("pull_request") or {}).get("body")
    changed_files = get_changed_files(args.base_ref)

    try:
        validate_pr_body(body, changed_files)
    except ModalReleaseConfigError as e:
        print(f"::error::{e}")
        return 1

    print("Modal release configuration is valid.")
    return 0


def validate_pr_body(
    body: str | None,
    changed_files: list[str],
    *,
    repo_root: Path | None = None,
) -> None:
    requires_config = changed_files_require_modal_release_config(changed_files)
    has_config = bool(body and CONFIG_KEY in body)
    validate_alembic_migration_changes(changed_files, repo_root=repo_root)

    if not requires_config and not has_config:
        print("No Modal release files changed; config block is optional.")
        return

    if requires_config and not has_config:
        raise ModalReleaseConfigError(
            "This PR changes Modal release files and must include a "
            "`modal_release` YAML block in the PR body"
        )

    parse_modal_release_config_from_body(body)


def validate_alembic_migration_changes(
    changed_files: list[str],
    *,
    repo_root: Path | None = None,
) -> None:
    root = repo_root or Path.cwd()
    for filename in changed_files:
        if not _is_alembic_version_file(filename):
            continue

        migration_path = root / filename
        if not migration_path.exists():
            raise ModalReleaseConfigError(
                "Alembic migration files must not be deleted in a normal "
                f"release PR: {filename}"
            )

        destructive_operations = _destructive_upgrade_operations(
            migration_path.read_text()
        )
        if destructive_operations:
            operations = ", ".join(sorted(destructive_operations))
            raise ModalReleaseConfigError(
                "Alembic migration upgrades in Modal release PRs must be "
                "backward-compatible while current and frontier workers are "
                f"both active. Found destructive operation(s) in {filename}: "
                f"{operations}."
            )


def _is_alembic_version_file(filename: str) -> bool:
    return filename.startswith("alembic/versions/") and filename.endswith(
        ".py"
    )


def _destructive_upgrade_operations(migration_text: str) -> set[str]:
    upgrade_text = _upgrade_function_text(migration_text)
    patterns = {
        "drop_column": r"\bdrop_column\s*\(",
        "drop_table": r"\bdrop_table\s*\(",
    }
    return {
        operation
        for operation, pattern in patterns.items()
        if re.search(pattern, upgrade_text)
    }


def _upgrade_function_text(migration_text: str) -> str:
    match = re.search(
        r"^def upgrade\(\).*?(?=^def downgrade\(\)|\Z)",
        migration_text,
        flags=re.DOTALL | re.MULTILINE,
    )
    return match.group(0) if match else ""


def get_changed_files(base_ref: str | None) -> list[str]:
    base_ref = base_ref or os.getenv("GITHUB_BASE_REF") or "main"
    commands = [
        ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
    ]

    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            continue
        return [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]

    raise RuntimeError(f"Unable to determine changed files from {base_ref}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Modal release configuration in a PR body."
    )
    parser.add_argument(
        "--event-path",
        default=os.getenv("GITHUB_EVENT_PATH"),
        required=os.getenv("GITHUB_EVENT_PATH") is None,
    )
    parser.add_argument("--base-ref")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
