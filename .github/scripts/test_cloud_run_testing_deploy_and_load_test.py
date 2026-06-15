import os
from pathlib import Path
import subprocess


def test_testing_deploy_script_deploys_smokes_and_load_tests(tmp_path):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "deploy-output.txt"
    _write_fake_command(tmp_path / "docker", log_path)
    _write_fake_command(tmp_path / "curl", log_path)
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_uv(tmp_path, log_path)
    _write_fake_deploy_script(tmp_path / "deploy.sh", log_path, output_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "GOOGLE_CLOUD_PROJECT": "policyengine-household-api",
        "USER": "Ada Lovelace",
        "HOUSEHOLD_CLOUD_RUN_TEST_DEPLOY_SCRIPT": str(tmp_path / "deploy.sh"),
        "HOUSEHOLD_CLOUD_RUN_LOAD_TEST_SCRIPT": "load-test.py",
        "GITHUB_SHA": "abc123",
    }

    result = subprocess.run(
        [".github/scripts/cloud-run-testing-deploy-and-load-test.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert "DEPLOY_ENV HOUSEHOLD_CLOUD_RUN_ENVIRONMENT=testing" in log
    assert (
        "DEPLOY_ENV HOUSEHOLD_CLOUD_RUN_SERVICE_PREFIX="
        "household-api-testing-ada-lovelace"
    ) in log
    assert (
        "DEPLOY_ENV HOUSEHOLD_FAILOVER_MANIFEST_BUCKET="
        "policyengine-household-api-release-manifests"
    ) in log
    assert (
        "DEPLOY_ENV HOUSEHOLD_FAILOVER_MANIFEST_BLOB="
        "testing/ada-lovelace/failover-manifest.json"
    ) in log
    assert "DEPLOY_ENV HOUSEHOLD_FAILOVER_FORCE_BACKEND=cloud_run" in log
    assert (
        "DEPLOY_ENV HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT="
        "987654321-compute@developer.gserviceaccount.com"
    ) in log
    assert (
        "DEPLOY_ENV HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT="
        "987654321-compute@developer.gserviceaccount.com"
    ) in log
    assert "curl -fsS https://testing-gateway.run.app/liveness_check" in log
    assert "curl -fsS https://testing-gateway.run.app/readiness_check" in log
    assert "uv run python load-test.py" in log
    assert "--base-url https://testing-gateway.run.app" in log
    assert "--requests 100 --concurrency 25" in log
    assert "--expected-backend cloud_run" in log
    assert "gateway_url=https://testing-gateway.run.app" in result.stdout


def test_testing_deploy_script_can_skip_deploy_and_disable_expected_backend(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    _write_fake_command(tmp_path / "docker", log_path)
    _write_fake_command(tmp_path / "curl", log_path)
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_uv(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET": "manifest-bucket",
        "HOUSEHOLD_CLOUD_RUN_TEST_ID": "scratch",
        "HOUSEHOLD_CLOUD_RUN_LOAD_TEST_SCRIPT": "load-test.py",
    }

    result = subprocess.run(
        [
            ".github/scripts/cloud-run-testing-deploy-and-load-test.sh",
            "--skip-deploy",
            "--expected-backend",
            "none",
            "--requests",
            "2",
            "--concurrency",
            "1",
        ],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        "gcloud run services describe household-api-testing-scratch-gateway"
        in log
    )
    assert "--requests 2 --concurrency 1" in log
    assert "--expected-backend" not in log


def test_testing_deploy_script_requires_project(tmp_path):
    log_path = tmp_path / "commands.log"
    _write_fake_command(tmp_path / "curl", log_path)
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_uv(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
    }
    env.pop("GOOGLE_CLOUD_PROJECT", None)

    result = subprocess.run(
        [".github/scripts/cloud-run-testing-deploy-and-load-test.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "GOOGLE_CLOUD_PROJECT is required" in result.stderr


def _write_fake_command(path: Path, log_path: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "$(basename "$0") $*" >> "{log_path}"
"""
    )
    path.chmod(0o755)


def _write_fake_gcloud(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "gcloud"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "gcloud $*" >> "{log_path}"
if [[ "$*" == projects\\ describe* ]]; then
  echo "987654321"
  exit 0
fi
if [[ "$*" == run\\ services\\ describe* ]]; then
  echo "https://described-gateway.run.app"
fi
"""
    )
    script.chmod(0o755)


def _write_fake_uv(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "uv"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv $*" >> "{log_path}"
"""
    )
    script.chmod(0o755)


def _write_fake_deploy_script(
    path: Path,
    log_path: Path,
    output_path: Path,
) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
env | sort | grep '^HOUSEHOLD_' | sed 's/^/DEPLOY_ENV /' >> "{log_path}"
echo "GITHUB_SHA=${{GITHUB_SHA}}" >> "{log_path}"
echo "gateway_url=https://testing-gateway.run.app" > "${{GITHUB_OUTPUT}}"
echo "gateway_url=https://testing-gateway.run.app" > "{output_path}"
"""
    )
    path.chmod(0o755)
