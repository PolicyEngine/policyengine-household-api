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
    assert resolved.deploy_mode == "release"
    assert resolved.config is not None


def test_resolve_release_ignores_template_guidance_without_config_block():
    resolved = resolve_release_from_event(
        {
            "pull_request": {
                "body": "Most PRs do not need `modal_release` config."
            }
        },
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
    )

    assert resolved.should_deploy is False
    assert resolved.source == "pull_request-missing"
    assert resolved.deploy_mode == "none"


def test_resolve_release_uses_workflow_dispatch_inputs():
    resolved = resolve_release_from_event(
        {
            "inputs": {
                "new_app_target": "current",
                "promote_existing_frontier": "false",
                "cleanup_target": "frontier",
            }
        },
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
        event_name="workflow_dispatch",
    )

    assert resolved.should_deploy is True
    assert resolved.source == "workflow-dispatch-inputs"
    assert resolved.deploy_mode == "release"
    assert resolved.config is not None
    assert resolved.config.new_app_target == "current"
    assert resolved.config.promote_existing_frontier is False
    assert resolved.config.cleanup_target == "frontier"


def test_resolve_release_accepts_both_workflow_dispatch_target():
    resolved = resolve_release_from_event(
        {
            "inputs": {
                "new_app_target": "both",
                "promote_existing_frontier": "false",
                "cleanup_target": "retired",
            }
        },
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
        event_name="workflow_dispatch",
    )

    assert resolved.should_deploy is True
    assert resolved.deploy_mode == "release"
    assert resolved.config is not None
    assert resolved.config.new_app_target == "both"
    assert resolved.config.promote_existing_frontier is False
    assert resolved.config.cleanup_target == "retired"


def test_resolve_release_uses_weekly_default_for_empty_workflow_dispatch():
    resolved = resolve_release_from_event(
        {"inputs": {}},
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
        event_name="workflow_dispatch",
    )

    assert resolved.should_deploy is True
    assert resolved.source == "workflow-dispatch-inputs"
    assert resolved.deploy_mode == "release"
    assert resolved.config is not None
    assert resolved.config.cleanup_target == "retired"


def test_resolve_release_skips_regular_push_even_with_pr_config():
    fetched = []

    resolved = resolve_release_from_event(
        {
            "repository": {
                "full_name": "PolicyEngine/policyengine-household-api"
            },
            "after": "abc123",
            "head_commit": {"message": "Regular merge"},
        },
        fetch_pr_body_for_commit=lambda repository, sha: (
            fetched.append((repository, sha)) or VALID_BODY
        ),
    )

    assert resolved.should_deploy is False
    assert resolved.source == "push-not-release-commit"
    assert resolved.deploy_mode == "none"
    assert fetched == []


def test_resolve_release_uses_versioning_parent_pr_body():
    def fetch_pr_body(repository, sha):
        assert repository == "PolicyEngine/policyengine-household-api"
        assert sha == "merge-sha"
        return VALID_BODY

    resolved = resolve_release_from_event(
        {
            "repository": {
                "full_name": "PolicyEngine/policyengine-household-api"
            },
            "before": "merge-sha",
            "after": "versioning-sha",
            "head_commit": {"message": WEEKLY_UPDATE_COMMIT_MESSAGE},
        },
        fetch_pr_body_for_commit=fetch_pr_body,
    )

    assert resolved.should_deploy is True
    assert resolved.source == "versioning-parent-pull-request"
    assert resolved.deploy_mode == "release"
    assert resolved.config is not None


def test_resolve_release_uses_code_deploy_when_no_pr_body_exists():
    resolved = resolve_release_from_event(
        {
            "repository": {
                "full_name": "PolicyEngine/policyengine-household-api"
            },
            "before": "merge-sha",
            "after": "abc123",
            "head_commit": {"message": WEEKLY_UPDATE_COMMIT_MESSAGE},
        },
        fetch_pr_body_for_commit=lambda _repository, _sha: None,
    )

    assert resolved.should_deploy is True
    assert resolved.source == "code-only"
    assert resolved.deploy_mode == "code"
    assert resolved.config is None
