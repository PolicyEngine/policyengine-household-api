import pytest

from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfigError,
    NewAppTarget,
    body_contains_modal_release_config,
    changed_files_require_modal_release_config,
    parse_modal_release_config_from_body,
    release_package_versions_changed,
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


def test_body_contains_config_ignores_template_guidance_without_yaml_block():
    assert not body_contains_modal_release_config(
        "A PR may mention `modal_release` in guidance text."
    )


def test_body_contains_config_accepts_fenced_yaml_block():
    assert body_contains_modal_release_config(VALID_BODY)


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


def test_changed_files_require_config_for_staged_deploy_workflow():
    assert changed_files_require_modal_release_config(
        [".github/workflows/deploy-staged.yml"]
    )


def test_changed_files_require_config_for_modal_channel_test_script():
    assert changed_files_require_modal_release_config(
        [".github/scripts/run-deployed-tests-for-modal-route.sh"]
    )


def test_changed_files_do_not_require_config_for_unrelated_paths():
    assert not changed_files_require_modal_release_config(["README.md"])


def test_release_package_versions_changed_detects_us_updates():
    base = """
[project]
dependencies = [
    "policyengine_uk==2.31.0",
    "policyengine_us==1.691.1",
]
"""
    head = """
[project]
dependencies = [
    "policyengine_uk==2.31.0",
    "policyengine_us==1.692.0",
]
"""

    assert release_package_versions_changed(base, head)


def test_release_package_versions_changed_ignores_other_country_updates():
    base = """
[project]
dependencies = [
    "policyengine_uk==2.31.0",
    "policyengine_us==1.691.1",
    "policyengine_canada==0.96.3",
]
"""
    head = """
[project]
dependencies = [
    "policyengine_uk==2.31.0",
    "policyengine_us==1.691.1",
    "policyengine_canada==0.97.0",
]
"""

    assert not release_package_versions_changed(base, head)
