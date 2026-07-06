from pathlib import Path

import pytest

from check_modal_release_alembic import validate_alembic_migration_changes
from policyengine_household_common.release_config import (
    ModalReleaseConfigError,
)

ALEMBIC_VERSIONS_DIR = (
    Path("libs/household-analytics/policyengine_household_analytics")
    / "alembic"
    / "versions"
)


def test_validate_alembic_rejects_destructive_upgrade(tmp_path):
    migration = tmp_path / ALEMBIC_VERSIONS_DIR / "20260520_0004_bad.py"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        """
def upgrade() -> None:
    op.drop_column("calculate_request_variables", "variable_name")


def downgrade() -> None:
    pass
"""
    )

    with pytest.raises(ModalReleaseConfigError, match="destructive"):
        validate_alembic_migration_changes(
            [
                "libs/household-analytics/policyengine_household_analytics/alembic/versions/20260520_0004_bad.py"
            ],
            repo_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (
            'op.execute("DROP TABLE visits")',
            "raw_drop_sql",
        ),
        (
            'op.execute(sa.text("DROP INDEX old_index"))',
            "raw_drop_sql",
        ),
        (
            'batch_op.drop_constraint("old_constraint")',
            "drop_constraint",
        ),
        (
            'batch_op.drop_index("old_index")',
            "drop_index",
        ),
        (
            'batch_op.alter_column("client_id", nullable=False)',
            "alter_column_nullable_false",
        ),
        (
            'batch_op.create_unique_constraint("uq_client", ["client_id"])',
            "create_unique_constraint",
        ),
    ],
)
def test_validate_alembic_rejects_other_incompatible_upgrades(
    tmp_path,
    operation,
    expected,
):
    migration = tmp_path / ALEMBIC_VERSIONS_DIR / "20260520_0004_bad.py"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        f"""
def upgrade() -> None:
    with op.batch_alter_table("visits") as batch_op:
        {operation}


def downgrade() -> None:
    pass
"""
    )

    with pytest.raises(ModalReleaseConfigError, match=expected):
        validate_alembic_migration_changes(
            [
                "libs/household-analytics/policyengine_household_analytics/alembic/versions/20260520_0004_bad.py"
            ],
            repo_root=tmp_path,
        )


def test_validate_alembic_allows_destructive_downgrade(tmp_path):
    migration = tmp_path / ALEMBIC_VERSIONS_DIR / "20260520_0004_good.py"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        """
def upgrade() -> None:
    op.add_column("visits", sa.Column("region", sa.String()))


def downgrade() -> None:
    op.drop_column("visits", "region")
"""
    )

    validate_alembic_migration_changes(
        [
            "libs/household-analytics/policyengine_household_analytics/alembic/versions/20260520_0004_good.py"
        ],
        repo_root=tmp_path,
    )
