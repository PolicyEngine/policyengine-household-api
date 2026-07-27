from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "backfill-pypi-libs.yml"
PYPI_PUBLISH_ACTION = "pypa/gh-action-pypi-publish@release/v1"


def test_backfill_accepts_only_a_release_version():
    workflow = _load_workflow()
    inputs = workflow[True]["workflow_dispatch"]["inputs"]

    assert set(inputs) == {"version"}
    assert inputs["version"]["required"] is True

    build_job = workflow["jobs"]["build"]
    checkout_steps = _steps_using(build_job, "actions/checkout@v7")

    assert len(checkout_steps) == 1
    assert checkout_steps[0]["with"]["ref"] == (
        "refs/tags/${{ inputs.version }}"
    )
    assert checkout_steps[0]["with"]["fetch-depth"] == 0

    run_scripts = "\n".join(
        step["run"] for step in build_job["steps"] if "run" in step
    )
    assert "^[0-9]+\\.[0-9]+\\.[0-9]+$" in run_scripts
    assert "+refs/heads/main:refs/remotes/origin/main" in run_scripts
    assert "git merge-base --is-ancestor HEAD origin/main" in run_scripts
    assert "https://pypi.org/pypi/policyengine-household-api/" in run_scripts


def test_backfill_build_cannot_request_pypi_credentials():
    workflow = _load_workflow()
    build_job = workflow["jobs"]["build"]

    assert build_job["permissions"] == {"contents": "read"}
    assert not _steps_using(build_job, PYPI_PUBLISH_ACTION)

    artifact_names = {
        step["with"]["name"]
        for step in _steps_using(build_job, "actions/upload-artifact@v7")
    }
    assert artifact_names == {
        "pypi-household-common",
        "pypi-household-analytics",
    }


def test_backfill_publishes_once_each_in_dependency_order():
    workflow = _load_workflow()
    jobs = workflow["jobs"]
    expected_jobs = {
        "publish-common": {
            "needs": ["build"],
            "artifact": "pypi-household-common",
        },
        "publish-analytics": {
            "needs": ["build", "publish-common"],
            "artifact": "pypi-household-analytics",
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


def _load_workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _steps_using(job, action):
    return [step for step in job["steps"] if step.get("uses") == action]
