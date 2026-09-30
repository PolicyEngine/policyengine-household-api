from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pr.yml"

EXPECTED_STATIC_AUTH_ENV = {
    "AUTH__ENABLED": "true",
    "AUTH0_ADDRESS_NO_DOMAIN": "test.invalid",
    "AUTH0_AUDIENCE_NO_DOMAIN": "https://household-api.test.invalid",
    "AUTH0_TEST_TOKEN_NO_DOMAIN": "ci-static-bearer-token",
    "AUTH0_TEST_TOKEN_SCOPES": "read:calculate-analytics",
}


def test_pull_request_workflow_has_read_only_repository_access():
    workflow = _load_workflow()

    assert workflow["permissions"] == {"contents": "read"}


def test_pull_request_workflow_does_not_reference_secrets():
    assert "secrets." not in WORKFLOW_PATH.read_text()


def test_pull_request_checkouts_do_not_persist_credentials():
    workflow = _load_workflow()
    checkout_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]

    assert checkout_steps
    for step in checkout_steps:
        assert step["with"]["persist-credentials"] is False


def test_pull_request_tests_do_not_authenticate_to_google_cloud():
    workflow = _load_workflow()
    actions = {
        step.get("uses", "") for step in workflow["jobs"]["test"]["steps"]
    }

    assert not any(
        action.startswith("google-github-actions/") for action in actions
    )


def test_pull_request_authenticated_tests_use_public_static_values():
    workflow = _load_workflow()
    auth_step = next(
        step
        for step in workflow["jobs"]["test"]["steps"]
        if step.get("run") == "make test-with-auth"
    )

    assert auth_step["env"] == EXPECTED_STATIC_AUTH_ENV
    assert "secrets." not in str(auth_step["env"])


def _load_workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text())
