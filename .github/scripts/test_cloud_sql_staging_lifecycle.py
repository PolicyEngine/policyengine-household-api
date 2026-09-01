from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(".github/scripts/cloud-sql-staging-lifecycle.sh")


def test_start_sets_always_and_requires_runnable_state(tmp_path):
    result, calls = _run_lifecycle(
        tmp_path,
        "start",
        describe_output="ALWAYS\tRUNNABLE",
    )

    assert result.returncode == 0
    assert calls == [
        "sql instances patch household-api-user-analytics-staging "
        "--project=policyengine-household-api --activation-policy=ALWAYS --quiet",
        "sql instances describe household-api-user-analytics-staging "
        "--project=policyengine-household-api "
        "--format=value(settings.activationPolicy,state)",
    ]
    assert "policy=ALWAYS, state=RUNNABLE" in result.stdout


def test_stop_sets_never_without_requiring_stopped_state(tmp_path):
    result, calls = _run_lifecycle(
        tmp_path,
        "stop",
        describe_output="NEVER\tRUNNABLE",
    )

    assert result.returncode == 0
    assert "--activation-policy=NEVER" in calls[0]
    assert "policy=NEVER, state=RUNNABLE" in result.stdout


def test_invalid_action_fails_before_calling_gcloud(tmp_path):
    result, calls = _run_lifecycle(tmp_path, "restart")

    assert result.returncode == 2
    assert calls == []
    assert "Unsupported action" in result.stderr


def test_patch_failure_is_returned_without_describing_instance(tmp_path):
    result, calls = _run_lifecycle(tmp_path, "start", patch_exit_code=1)

    assert result.returncode == 1
    assert len(calls) == 1
    assert "sql instances patch" in calls[0]


def test_start_fails_when_instance_is_not_runnable(tmp_path):
    result, _ = _run_lifecycle(
        tmp_path,
        "start",
        describe_output="ALWAYS\tPENDING_CREATE",
    )

    assert result.returncode == 1
    assert "expected RUNNABLE" in result.stderr


def test_lifecycle_fails_when_activation_policy_does_not_match(tmp_path):
    result, _ = _run_lifecycle(
        tmp_path,
        "stop",
        describe_output="ALWAYS\tRUNNABLE",
    )

    assert result.returncode == 1
    assert "expected NEVER" in result.stderr


def test_lifecycle_rejects_alternate_project(tmp_path):
    result, calls = _run_lifecycle(
        tmp_path,
        "stop",
        extra_env={"CLOUD_SQL_PROJECT": "policyengine-api"},
    )

    assert result.returncode == 2
    assert calls == []
    assert "unexpected Cloud SQL project" in result.stderr


def test_lifecycle_rejects_alternate_instance(tmp_path):
    result, calls = _run_lifecycle(
        tmp_path,
        "stop",
        extra_env={"CLOUD_SQL_INSTANCE": "household-api-user-analytics"},
    )

    assert result.returncode == 2
    assert calls == []
    assert "unexpected Cloud SQL instance" in result.stderr


def _run_lifecycle(
    tmp_path,
    action: str,
    *,
    describe_output: str = "ALWAYS\tRUNNABLE",
    patch_exit_code: int = 0,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    calls_file = tmp_path / "gcloud-calls.txt"
    fake_gcloud = tmp_path / "gcloud"
    fake_gcloud.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${FAKE_GCLOUD_CALLS}"
if [[ "$1 $2 $3" == "sql instances patch" ]]; then
  exit "${FAKE_PATCH_EXIT_CODE}"
fi
if [[ "$1 $2 $3" == "sql instances describe" ]]; then
  printf '%b\\n' "${FAKE_DESCRIBE_OUTPUT}"
  exit 0
fi
exit 99
"""
    )
    fake_gcloud.chmod(0o755)
    env = {
        **os.environ,
        "GCLOUD_BIN": str(fake_gcloud),
        "FAKE_GCLOUD_CALLS": str(calls_file),
        "FAKE_PATCH_EXIT_CODE": str(patch_exit_code),
        "FAKE_DESCRIBE_OUTPUT": describe_output,
        **(extra_env or {}),
    }

    result = subprocess.run(
        ["bash", str(SCRIPT), action],
        capture_output=True,
        env=env,
        text=True,
    )
    calls = calls_file.read_text().splitlines() if calls_file.exists() else []
    return result, calls
