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
