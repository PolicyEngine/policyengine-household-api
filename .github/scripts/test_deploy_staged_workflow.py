from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "deploy-staged.yml"

EXPECTED_SLACK_ENV = {
    "HOUSEHOLD_FAILOVER_SLACK_WEBHOOK_URL": (
        "${{ secrets.HOUSEHOLD_FAILOVER_SLACK_WEBHOOK_URL }}"
    ),
    "HOUSEHOLD_FAILOVER_SLACK_TIMEOUT_SECONDS": (
        "${{ vars.HOUSEHOLD_FAILOVER_SLACK_TIMEOUT_SECONDS }}"
    ),
    "HOUSEHOLD_FAILOVER_SLACK_COOLDOWN_SECONDS": (
        "${{ vars.HOUSEHOLD_FAILOVER_SLACK_COOLDOWN_SECONDS }}"
    ),
}


def test_cloud_run_deploy_jobs_pass_slack_alert_environment():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text())

    for job_id in (
        "deploy-cloud-run-staging",
        "deploy-cloud-run-production",
    ):
        env = _deploy_step_env(workflow, job_id)

        for key, value in EXPECTED_SLACK_ENV.items():
            assert env[key] == value


def _deploy_step_env(workflow, job_id):
    job = workflow["jobs"][job_id]
    deploy_steps = [
        step
        for step in job["steps"]
        if step.get("name") == "Deploy Cloud Run failover services"
    ]

    assert len(deploy_steps) == 1
    return deploy_steps[0]["env"]
