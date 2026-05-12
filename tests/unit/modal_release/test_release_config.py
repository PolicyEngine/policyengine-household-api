import pytest

from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfigError,
    NewAppTarget,
    changed_files_require_modal_release_config,
    parse_modal_release_config_from_body,
)


VALID_BODY = """
## Modal release

```yaml
modal_release:
  new_app_target: frontier
  promote_existing_frontier: true
  cleanup_target: none
```
"""


def test_parse_modal_release_config_from_fenced_yaml():
    config = parse_modal_release_config_from_body(VALID_BODY)

    assert config.new_app_target == NewAppTarget.FRONTIER
    assert config.promote_existing_frontier is True


def test_parse_rejects_missing_config():
    with pytest.raises(ModalReleaseConfigError, match="modal_release"):
        parse_modal_release_config_from_body("## Summary\n")


def test_parse_rejects_invalid_promotion_combination():
    with pytest.raises(ModalReleaseConfigError, match="may only be true"):
        parse_modal_release_config_from_body(
            """
```yaml
modal_release:
  new_app_target: current
  promote_existing_frontier: true
  cleanup_target: none
```
"""
        )


def test_parse_rejects_active_cleanup_in_pr_config():
    with pytest.raises(ModalReleaseConfigError, match="may not be"):
        parse_modal_release_config_from_body(
            """
```yaml
modal_release:
  new_app_target: none
  promote_existing_frontier: false
  cleanup_target: current
```
"""
        )


def test_changed_files_require_config_for_modal_release_paths():
    assert changed_files_require_modal_release_config(
        ["policyengine_household_api/modal_release/gateway.py"]
    )


def test_changed_files_do_not_require_config_for_unrelated_paths():
    assert not changed_files_require_modal_release_config(["README.md"])
