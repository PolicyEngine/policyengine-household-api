from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from modal_release_check_common import (
    get_changed_files,
    get_file_at_ref,
    parse_changed_files_args,
)
from policyengine_household_common.release_config import (
    ModalReleaseConfigError,
)


def main() -> int:
    args = parse_changed_files_args(
        "Validate Alembic migrations for Modal release compatibility."
    )
    changed_files = get_changed_files(args.base_ref)

    try:
        validate_alembic_migration_changes(
            changed_files, base_ref=args.base_ref
        )
    except ModalReleaseConfigError as e:
        print(f"::error::{e}")
        return 1

    print("Alembic migration compatibility is valid.")
    return 0


def validate_alembic_migration_changes(
    changed_files: list[str],
    *,
    repo_root: Path | None = None,
    base_ref: str | None = None,
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

        if _is_unchanged_relocation(migration_path, filename, base_ref):
            # Historical migrations moved verbatim (e.g. from the pre-
            # workspace alembic/versions/ location) predate this rule and
            # are not re-validated.
            continue

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


LEGACY_ALEMBIC_VERSIONS_PREFIX = "alembic/versions/"


def _is_unchanged_relocation(
    migration_path: Path,
    filename: str,
    base_ref: str | None,
) -> bool:
    legacy_path = LEGACY_ALEMBIC_VERSIONS_PREFIX + Path(filename).name
    try:
        base_content = get_file_at_ref(legacy_path, base_ref)
    except Exception:
        return False
    return base_content == migration_path.read_text()


def _is_alembic_version_file(filename: str) -> bool:
    return filename.startswith(
        "libs/household-analytics/policyengine_household_analytics/alembic/versions/"
    ) and filename.endswith(".py")


def _destructive_upgrade_operations(migration_text: str) -> set[str]:
    upgrade_text = _upgrade_function_text(migration_text)
    try:
        parsed = ast.parse(upgrade_text)
    except SyntaxError:
        return {"unparseable_upgrade"}

    destructive_operations = set()
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call):
            continue

        call_name = _call_name(node.func)
        if call_name in {
            "drop_column",
            "drop_constraint",
            "drop_index",
            "drop_table",
        }:
            destructive_operations.add(call_name)
        if call_name in {
            "create_check_constraint",
            "create_unique_constraint",
        }:
            destructive_operations.add(call_name)
        if call_name == "alter_column" and _sets_nullable_false(node):
            destructive_operations.add("alter_column_nullable_false")
        if call_name in {
            "execute",
            "exec_driver_sql",
        } and _contains_raw_drop_sql(node):
            destructive_operations.add("raw_drop_sql")

    return destructive_operations


def _upgrade_function_text(migration_text: str) -> str:
    match = re.search(
        r"^def upgrade\(\).*?(?=^def downgrade\(\)|\Z)",
        migration_text,
        flags=re.DOTALL | re.MULTILINE,
    )
    return match.group(0) if match else ""


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _sets_nullable_false(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg == "nullable" and isinstance(
            keyword.value, ast.Constant
        ):
            return keyword.value.value is False
    return False


def _contains_raw_drop_sql(call: ast.Call) -> bool:
    for node in [*call.args, *(keyword.value for keyword in call.keywords)]:
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(
                child.value, str
            ):
                if re.search(r"\bDROP\s+", child.value, flags=re.IGNORECASE):
                    return True
    return False


if __name__ == "__main__":
    sys.exit(main())
