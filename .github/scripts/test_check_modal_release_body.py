import pytest

from check_modal_release_body import validate_release_body_config
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


def test_validate_release_body_allows_missing_config_for_unrelated_files():
    validate_release_body_config(None, ["README.md"])


def test_validate_release_body_requires_config_for_modal_release_files():
    with pytest.raises(ModalReleaseConfigError, match="must include"):
        validate_release_body_config(
            None,
            ["policyengine_household_api/modal_release/gateway.py"],
        )


def test_validate_release_body_accepts_config_for_modal_release_files():
    validate_release_body_config(
        VALID_BODY,
        ["policyengine_household_api/modal_release/gateway.py"],
    )


def test_validate_release_body_rejects_invalid_config_even_for_unrelated_files():
    with pytest.raises(ModalReleaseConfigError, match="may only be true"):
        validate_release_body_config(
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


def test_validate_release_body_allows_template_guidance_without_config_block():
    validate_release_body_config(
        "Modal release guidance may mention current/frontier workers.",
        ["README.md"],
    )
