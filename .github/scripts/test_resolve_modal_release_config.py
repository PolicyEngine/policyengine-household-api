from resolve_modal_release_config import (
    WEEKLY_UPDATE_COMMIT_MESSAGE,
    resolve_release_from_event,
)


VALID_BODY = """
```yaml
modal_release:
  new_app_target: frontier
  promote_existing_frontier: true
  cleanup_target: none
```
"""


def test_resolve_release_from_pull_request_body():
    resolved = resolve_release_from_event(
        {"pull_request": {"body": VALID_BODY}},
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
    )

    assert resolved.should_deploy is True
    assert resolved.config is not None


def test_resolve_release_skips_push_without_config_or_weekly_message():
    resolved = resolve_release_from_event(
        {
            "repository": {
                "full_name": "PolicyEngine/policyengine-household-api"
            },
            "after": "abc123",
            "head_commit": {"message": "Regular merge"},
        },
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
    )

    assert resolved.should_deploy is False


def test_resolve_release_uses_weekly_default_when_no_pr_body_exists():
    resolved = resolve_release_from_event(
        {
            "repository": {
                "full_name": "PolicyEngine/policyengine-household-api"
            },
            "after": "abc123",
            "head_commit": {"message": WEEKLY_UPDATE_COMMIT_MESSAGE},
        },
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
    )

    assert resolved.should_deploy is True
    assert resolved.source == "weekly-default"
