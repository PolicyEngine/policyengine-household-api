import os
from pathlib import Path
import subprocess


def _base_env(tmp_path: Path, output_path: Path) -> dict:
    return {
        # Strip inherited observability vars so the assertions below see
        # exactly the values this test sets, not developer-shell state.
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OBSERVABILITY_")
        },
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "UV_BIN": str(tmp_path / "uv"),
        "DOCKER_BIN": str(tmp_path / "docker"),
        "GCLOUD_BIN": str(tmp_path / "gcloud"),
        "GITHUB_OUTPUT": str(output_path),
        "GITHUB_SHA": "abc123",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "ANALYTICS__ENABLED": "true",
        "HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT": (
            "household-api-analytics-writer@policyengine-test.iam.gserviceaccount.com"
        ),
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics@password,with,comma",
        "OBSERVABILITY_ENABLED": "true",
        "OBSERVABILITY_LOG_RAW_IP": "false",
        "OBSERVABILITY_REQUEST_LOGS_ENABLED": "true",
    }


def test_cloud_run_deploy_analytics_deploys_writer_with_startup_probe(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        "docker build --file gcp/cloud_run/analytics_writer.Dockerfile" in log
    )
    assert "docker push" in log
    assert "gcloud run deploy household-api-staging-analytics-writer" in log
    assert "--no-allow-unauthenticated" in log
    assert "--timeout 300" in log
    assert (
        "--service-account "
        "household-api-analytics-writer@policyengine-test.iam.gserviceaccount.com"
        in log
    )
    assert "APP__ENVIRONMENT: |-" in log
    assert "  staging" in log
    assert "OBSERVABILITY_PLATFORM: |-" in log
    # GOOGLE_CLOUD_PROJECT is the runtime project here; the log sink must
    # fall back to the fixed dedicated project instead of drifting to it.
    assert (
        "OBSERVABILITY_GOOGLE_CLOUD_PROJECT: |-\n"
        "  policyengine-observability\n"
    ) in log
    # Unset observability knobs must be omitted so the package's clamped
    # defaults govern at runtime.
    assert "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME" not in log
    assert "WEB_TIMEOUT: |-" in log
    assert "USER_ANALYTICS_DB_CONNECTION_NAME: |-" in log
    assert (
        "--set-secrets=USER_ANALYTICS_DB_PASSWORD="
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD:latest" in log
    )
    assert "analytics@password,with,comma" not in log
    assert "cloud_run_apply_startup_probe.py" in log
    assert (
        "--path /liveness_check --period-seconds 2 "
        "--timeout-seconds 2 --failure-threshold 30" in log
    )
    assert "gcloud run services replace" in log
    assert (
        "analytics_writer_url="
        "https://household-api-staging-analytics-writer.run.app"
        in output_path.read_text()
    )


def test_cloud_run_deploy_analytics_skips_when_analytics_disabled(tmp_path):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)
    env["ANALYTICS__ENABLED"] = "false"
    env.pop("HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "skipping Cloud Run analytics writer deploy" in result.stdout
    assert not log_path.exists()
    assert not output_path.exists()


def test_cloud_run_deploy_analytics_requires_writer_service_account(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_gcloud(tmp_path, log_path)
    env = _base_env(tmp_path, output_path)
    env.pop("HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-analytics.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert (
        "HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT" in result.stdout
    )


def _write_fake_uv(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "uv"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv $*" >> "{log_path}"
"""
    )
    script.chmod(0o755)


def _write_fake_docker(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "docker"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >> "{log_path}"
"""
    )
    script.chmod(0o755)


def _write_fake_gcloud(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "gcloud"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "gcloud $*" >> "{log_path}"

for arg in "$@"; do
  if [[ "${{arg}}" == --env-vars-file=* ]]; then
    echo "env-vars-file ${{arg#--env-vars-file=}}" >> "{log_path}"
    cat "${{arg#--env-vars-file=}}" >> "{log_path}"
  fi
done

if [[ "$*" == artifacts\\ repositories\\ describe* ]]; then
  exit 0
fi

if [[ "$*" == run\\ services\\ describe* ]]; then
  service="$4"
  echo "https://${{service}}.run.app"
  exit 0
fi

exit 0
"""
    )
    script.chmod(0o755)
