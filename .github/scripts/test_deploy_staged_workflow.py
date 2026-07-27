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
PYPI_PUBLISH_ACTION = "pypa/gh-action-pypi-publish@release/v1"


def test_cloud_run_deploy_jobs_pass_slack_alert_environment():
    workflow = _load_workflow()

    for job_id in (
        "deploy-cloud-run-staging",
        "deploy-cloud-run-production",
    ):
        env = _deploy_step_env(workflow, job_id)

        for key, value in EXPECTED_SLACK_ENV.items():
            assert env[key] == value


def test_pypi_distributions_are_built_without_oidc_permission():
    workflow = _load_workflow()
    job = workflow["jobs"]["build-pypi-distributions"]

    assert job["permissions"] == {"contents": "read"}
    assert not _steps_using(job, PYPI_PUBLISH_ACTION)

    artifact_names = {
        step["with"]["name"]
        for step in _steps_using(job, "actions/upload-artifact@v7")
    }
    assert artifact_names == {
        "pypi-household-common",
        "pypi-household-analytics",
        "pypi-household-api",
    }


def test_pypi_packages_publish_once_each_in_dependency_order():
    workflow = _load_workflow()
    jobs = workflow["jobs"]
    expected_jobs = {
        "publish-common": {
            "needs": ["build-pypi-distributions"],
            "artifact": "pypi-household-common",
        },
        "publish-analytics": {
            "needs": ["build-pypi-distributions", "publish-common"],
            "artifact": "pypi-household-analytics",
        },
        "publish-api": {
            "needs": ["build-pypi-distributions", "publish-analytics"],
            "artifact": "pypi-household-api",
        },
    }

    for job_id, expected in expected_jobs.items():
        job = jobs[job_id]

        assert job["needs"] == expected["needs"]
        assert job["permissions"] == {"id-token": "write"}
        assert len(_steps_using(job, PYPI_PUBLISH_ACTION)) == 1
        assert not [step for step in job["steps"] if "run" in step]

        downloads = _steps_using(job, "actions/download-artifact@v8")
        assert len(downloads) == 1
        assert downloads[0]["with"]["name"] == expected["artifact"]

    assert "publish-api" in jobs["tag-release"]["needs"]


def _load_workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _steps_using(job, action):
    return [step for step in job["steps"] if step.get("uses") == action]


def _deploy_step_env(workflow, job_id):
    job = workflow["jobs"][job_id]
    deploy_steps = [
        step
        for step in job["steps"]
        if step.get("name") == "Deploy Cloud Run failover services"
    ]

    assert len(deploy_steps) == 1
    return deploy_steps[0]["env"]
