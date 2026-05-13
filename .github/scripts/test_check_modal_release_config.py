import pytest

from check_modal_release_config import validate_pr_body
from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfigError,
)


VALID_BODY = """
```yaml
modal_release:
  new_app_target: frontier
  promote_existing_frontier: true
  cleanup_target: none
```
"""


def test_validate_pr_body_allows_missing_config_for_unrelated_files():
    validate_pr_body(None, ["README.md"])


def test_validate_pr_body_requires_config_for_modal_release_files():
    with pytest.raises(ModalReleaseConfigError, match="must include"):
        validate_pr_body(
            None,
            ["policyengine_household_api/modal_release/gateway.py"],
        )


def test_validate_pr_body_accepts_config_for_modal_release_files():
    validate_pr_body(
        VALID_BODY,
        ["policyengine_household_api/modal_release/gateway.py"],
    )


def test_validate_pr_body_rejects_invalid_config_even_for_unrelated_files():
    with pytest.raises(ModalReleaseConfigError, match="may only be true"):
        validate_pr_body(
            """
```yaml
modal_release:
  new_app_target: current
  promote_existing_frontier: true
  cleanup_target: none
```
""",
            ["README.md"],
        )


def test_validate_pr_body_rejects_destructive_alembic_upgrade(tmp_path):
    migration = tmp_path / "alembic" / "versions" / "20260520_0004_bad.py"
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
        validate_pr_body(
            VALID_BODY,
            ["alembic/versions/20260520_0004_bad.py"],
            repo_root=tmp_path,
        )


def test_validate_pr_body_allows_destructive_alembic_downgrade(tmp_path):
    migration = tmp_path / "alembic" / "versions" / "20260520_0004_good.py"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        """
def upgrade() -> None:
    op.add_column("visits", sa.Column("region", sa.String()))


def downgrade() -> None:
    op.drop_column("visits", "region")
"""
    )

    validate_pr_body(
        VALID_BODY,
        ["alembic/versions/20260520_0004_good.py"],
        repo_root=tmp_path,
    )
