import os
from pathlib import Path
import subprocess


def test_cloud_run_warm_workers_warms_liveness_and_gateway_calculate(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_curl(tmp_path, log_path)

    env = {
        **os.environ,
        "GCLOUD_BIN": str(tmp_path / "gcloud"),
        "CURL_BIN": str(tmp_path / "curl"),
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "CLOUD_RUN_GATEWAY_SERVICE": "household-api-staging-gateway",
        "HOUSEHOLD_API_BASE_URL": "https://gateway.run.app",
        "HOUSEHOLD_API_AUTH_TOKEN": "auth-token",
        "HOUSEHOLD_CLOUD_RUN_WARM_CHANNELS": "current frontier",
    }

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-warm-workers.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert (
        "gcloud run services describe "
        "household-api-staging-current-worker" in log
    )
    assert (
        "gcloud run services describe "
        "household-api-staging-frontier-worker" in log
    )
    assert (
        "curl -sS -o /dev/null -w %{http_code} --max-time 240 "
        "-H Authorization: Bearer identity-token "
        "https://household-api-staging-current-worker.run.app/liveness_check"
        in log
    )
    assert (
        "curl -sS -o /dev/null -w %{http_code} --max-time 240 "
        "-H Authorization: Bearer identity-token "
        "https://household-api-staging-frontier-worker.run.app/liveness_check"
        in log
    )
    assert (
        "curl -sS -o /dev/null -w %{http_code} --max-time 240 "
        "-X POST -H Authorization: Bearer auth-token "
        "-H Content-Type: application/json" in log
    )
    assert "https://gateway.run.app/us/calculate" in log
    assert '"version":"current"' in log
    assert '"version":"frontier"' in log


def test_cloud_run_warm_workers_warms_gateway_calculates_in_parallel(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_curl(tmp_path, log_path)

    env = {
        **os.environ,
        "GCLOUD_BIN": str(tmp_path / "gcloud"),
        "CURL_BIN": str(tmp_path / "curl"),
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "CLOUD_RUN_GATEWAY_SERVICE": "household-api-staging-gateway",
        "HOUSEHOLD_API_BASE_URL": "https://gateway.run.app",
        "HOUSEHOLD_API_AUTH_TOKEN": "auth-token",
        "HOUSEHOLD_CLOUD_RUN_WARM_CHANNELS": "current frontier",
        "FAKE_CURL_CALCULATE_SLEEP": "0.2",
    }

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-warm-workers.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    lines = log_path.read_text().splitlines()
    current_start = lines.index("calculate-start current")
    frontier_start = lines.index("calculate-start frontier")
    first_end = min(
        lines.index("calculate-end current"),
        lines.index("calculate-end frontier"),
    )
    assert current_start < first_end
    assert frontier_start < first_end


def _write_fake_gcloud(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "gcloud"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "gcloud $*" >> "{log_path}"

if [[ "$*" == run\\ services\\ describe* ]]; then
  echo "https://$4.run.app"
  exit 0
fi

if [[ "$*" == auth\\ print-identity-token* ]]; then
  echo "identity-token"
  exit 0
fi
"""
    )
    script.chmod(0o755)


def _write_fake_curl(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "curl"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "curl $*" >> "{log_path}"
if [[ "$*" == *"/us/calculate"* ]]; then
  channel="unknown"
  if [[ "$*" == *'"version":"current"'* ]]; then
    channel="current"
  elif [[ "$*" == *'"version":"frontier"'* ]]; then
    channel="frontier"
  fi
  echo "calculate-start ${{channel}}" >> "{log_path}"
  if [ -n "${{FAKE_CURL_CALCULATE_SLEEP:-}}" ]; then
    sleep "${{FAKE_CURL_CALCULATE_SLEEP}}"
  fi
  echo "calculate-end ${{channel}}" >> "{log_path}"
fi
printf '200'
"""
    )
    script.chmod(0o755)
