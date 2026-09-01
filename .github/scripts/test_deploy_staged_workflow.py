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
EXPECTED_AUTH0_ENV = {
    "AUTH0_ADDRESS_NO_DOMAIN": "${{ secrets.AUTH0_ADDRESS_NO_DOMAIN }}",
    "AUTH0_AUDIENCE_NO_DOMAIN": "${{ secrets.AUTH0_AUDIENCE_NO_DOMAIN }}",
}
PYPI_PUBLISH_ACTION = "pypa/gh-action-pypi-publish@release/v1"
CLOUD_SQL_LIFECYCLE_SCRIPT = "cloud-sql-staging-lifecycle.sh"


def test_cloud_run_deploy_jobs_pass_slack_alert_environment():
    workflow = _load_workflow()

    for job_id in (
        "deploy-cloud-run-staging",
        "deploy-cloud-run-production",
    ):
        env = _deploy_step_env(workflow, job_id)

        for key, value in EXPECTED_SLACK_ENV.items():
            assert env[key] == value


def test_policyengine_cloud_run_deploy_jobs_pass_auth0_environment():
    workflow = _load_workflow()

    for job_id in (
        "deploy-cloud-run-staging",
        "deploy-cloud-run-production",
    ):
        env = _deploy_step_env(workflow, job_id)

        for key, value in EXPECTED_AUTH0_ENV.items():
            assert env[key] == value


def test_deployed_api_tests_only_use_cloud_run_gateway():
    workflow = _load_workflow()
    jobs = workflow["jobs"]

    assert "integration-tests-staging" not in jobs
    for job_id in (
        "integration-tests-cloud-run-staging",
        "integration-tests-cloud-run-fallback-staging",
    ):
        run_commands = "\n".join(
            step.get("run", "") for step in jobs[job_id]["steps"]
        )
        assert "run-deployed-tests-for-cloud-run-route.sh" in run_commands
        assert "run-deployed-tests-for-modal-route.sh" not in run_commands

    production_dependencies = jobs["gate-production"]["needs"]
    assert "integration-tests-staging" not in production_dependencies
    assert "integration-tests-cloud-run-staging" in production_dependencies
    assert (
        "integration-tests-cloud-run-fallback-staging"
        in production_dependencies
    )


def test_staging_cloud_sql_lifecycle_wraps_deploy_and_tests():
    workflow = _load_workflow()
    jobs = workflow["jobs"]
    start_job = jobs["start-analytics-db-staging"]
    migration_job = jobs["migrate-analytics-db-staging"]
    stop_job = jobs["stop-analytics-db-staging"]

    assert start_job["needs"] == [
        "lint-and-test",
        "resolve-modal-release-config",
    ]
    assert start_job["timeout-minutes"] == 15
    assert (
        _run_commands(start_job)
        .strip()
        .endswith(f"{CLOUD_SQL_LIFECYCLE_SCRIPT} start")
    )

    assert migration_job["needs"] == [
        "resolve-modal-release-config",
        "start-analytics-db-staging",
    ]

    assert stop_job["needs"] == [
        "resolve-modal-release-config",
        "integration-tests-cloud-run-staging",
        "integration-tests-cloud-run-fallback-staging",
    ]
    assert "always()" in stop_job["if"]
    assert stop_job["timeout-minutes"] == 15
    assert (
        _run_commands(stop_job)
        .strip()
        .endswith(f"{CLOUD_SQL_LIFECYCLE_SCRIPT} stop")
    )

    production_dependencies = jobs["gate-production"]["needs"]
    assert "stop-analytics-db-staging" in production_dependencies
    assert "integration-tests-cloud-run-staging" in production_dependencies
    assert (
        "integration-tests-cloud-run-fallback-staging"
        in production_dependencies
    )


def test_only_staging_database_lifecycle_jobs_call_helper():
    workflow = _load_workflow()
    jobs_using_helper = {
        job_id
        for job_id, job in workflow["jobs"].items()
        if CLOUD_SQL_LIFECYCLE_SCRIPT in _run_commands(job)
    }

    assert jobs_using_helper == {
        "start-analytics-db-staging",
        "stop-analytics-db-staging",
    }


def test_staging_database_lifecycle_also_applies_to_manual_dispatch():
    workflow = _load_workflow()

    assert "workflow_dispatch" in workflow[True]
    for job_id in (
        "start-analytics-db-staging",
        "stop-analytics-db-staging",
    ):
        condition = workflow["jobs"][job_id]["if"]
        assert "github.event_name" not in condition
        assert "inputs.deploy_scope" not in condition


def test_staging_migration_waits_for_connectivity_before_upgrade():
    workflow = _load_workflow()
    migration_steps = workflow["jobs"]["migrate-analytics-db-staging"]["steps"]
    wait_step = next(
        step
        for step in migration_steps
        if step.get("name") == "Wait for analytics database connectivity"
    )
    migration_step = next(
        step
        for step in migration_steps
        if step.get("name") == "Run analytics database migrations"
    )

    assert "timeout 300s" in wait_step["run"]
    assert "alembic" in wait_step["run"]
    assert "current" in wait_step["run"]
    assert "upgrade" not in wait_step["run"]
    assert "upgrade head" in migration_step["run"]


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


def _run_commands(job):
    return "\n".join(step.get("run", "") for step in job["steps"])


def _deploy_step_env(workflow, job_id):
    job = workflow["jobs"][job_id]
    deploy_steps = [
        step
        for step in job["steps"]
        if step.get("name") == "Deploy Cloud Run failover services"
    ]

    assert len(deploy_steps) == 1
    return deploy_steps[0]["env"]
