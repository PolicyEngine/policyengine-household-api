import os
from pathlib import Path
import subprocess


def test_cloud_run_gateway_image_installs_observability_dependency():
    dockerfile = Path("gcp/cloud_run/gateway.Dockerfile").read_text()

    assert '"policyengine-observability[flask]>=1.0.0"' in dockerfile
    assert "numpy" not in dockerfile


def test_cloud_run_deploy_failover_deploys_workers_manifest_and_gateway(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_curl(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "UV_BIN": str(tmp_path / "uv"),
        "DOCKER_BIN": str(tmp_path / "docker"),
        "GCLOUD_BIN": str(tmp_path / "gcloud"),
        "CURL_BIN": str(tmp_path / "curl"),
        "GITHUB_OUTPUT": str(output_path),
        "GITHUB_SHA": "abc123",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET": "manifest-bucket",
        "MODAL_TOKEN_ID": "modal-token-id@example",
        "MODAL_TOKEN_SECRET": "modal-token,secret@example",
        "HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT": (
            "household-api-gateway@policyengine-test.iam.gserviceaccount.com"
        ),
        "HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT": (
            "household-api-worker@policyengine-test.iam.gserviceaccount.com"
        ),
        "AUTH__ENABLED": "true",
        "AUTH0_ADDRESS_NO_DOMAIN": "auth.example.com",
        "AUTH0_AUDIENCE_NO_DOMAIN": "api.example.com",
        "ANALYTICS__ENABLED": "true",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics@password,with,comma",
        "HOUSEHOLD_FAILOVER_MODAL_REQUEST_TIMEOUT_SECONDS": "45",
        "HOUSEHOLD_FAILOVER_MODAL_PROBE_TIMEOUT_SECONDS": "5",
        "HOUSEHOLD_MODAL_CANARY_APP_NAME": "household-canary",
        "HOUSEHOLD_FAILOVER_MODAL_CANARY_FUNCTION_NAME": "ping",
        "HOUSEHOLD_FAILOVER_MODAL_CANARY_TIMEOUT_SECONDS": "4",
        "HOUSEHOLD_FAILOVER_MODAL_FAILURE_MIN_COUNT": "10",
        "HOUSEHOLD_FAILOVER_MODAL_FAILURE_RATE": "0.5",
        "HOUSEHOLD_FAILOVER_MODAL_FAILURE_WINDOW_SECONDS": "60",
        "HOUSEHOLD_FAILOVER_MODAL_MIN_OPEN_SECONDS": "60",
        "HOUSEHOLD_FAILOVER_MODAL_RECOVERY_SUCCESSES": "3",
        "OBSERVABILITY_ENABLED": "true",
        "OBSERVABILITY_GOOGLE_CLOUD_PROJECT": "policyengine-observability",
        "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME": "policyengine-observability",
        "OBSERVABILITY_LOG_RAW_IP": "false",
        "OBSERVABILITY_LOG_DESTINATIONS": "stdout",
        "OBSERVABILITY_METRIC_ATTRIBUTE_KEYS": "ignored",
        "OBSERVABILITY_REQUEST_LOGS_ENABLED": "true",
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.com",
        "OTEL_EXPORTER_OTLP_HEADERS": "api-key=ignored",
        "OTEL_EXPORTER_OTLP_INSECURE": "false",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_SERVICE_NAME": "ignored",
    }

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-failover.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert "docker build --file gcp/cloud_run/worker.Dockerfile" in log
    assert (
        'HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON={"uk":"2.88.18","us":"2.0.0"}'
        in log
    )
    assert "gcloud run deploy household-api-staging-current-worker" in log
    assert "gcloud run deploy household-api-staging-frontier-worker" in log
    assert "--no-allow-unauthenticated --min-instances 0" in log
    assert "--concurrency 5" in log
    assert log.count("--timeout 1200") == 3
    assert "WEB_TIMEOUT: |-" in log
    assert "OBSERVABILITY_ENVIRONMENT: |-" in log
    assert "  staging" in log
    assert "OBSERVABILITY_PLATFORM: |-" in log
    assert "  google_cloud_run" in log
    assert "OBSERVABILITY_GOOGLE_CLOUD_PROJECT: |-" in log
    assert "  policyengine-observability" in log
    assert "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME: |-" in log
    assert "OBSERVABILITY_ENABLED: |-" in log
    assert "OBSERVABILITY_LOG_DESTINATIONS: |-" in log
    assert "OBSERVABILITY_LOG_RAW_IP: |-" in log
    assert "OBSERVABILITY_REQUEST_LOGS_ENABLED: |-" in log
    assert "OBSERVABILITY_METRIC_ATTRIBUTE_KEYS" not in log
    assert "OTEL_ENABLED" not in log
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in log
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in log
    assert "OTEL_EXPORTER_OTLP_INSECURE" not in log
    assert "OTEL_EXPORTER_OTLP_PROTOCOL" not in log
    assert "OTEL_SERVICE_NAME" not in log
    assert "cloud_run_apply_scaling_controls.py" in log
    assert "--scaling-concurrency-target 0.3" in log
    assert "gcloud run services replace" in log
    assert "--env-vars-file=" in log
    assert "--set-env-vars" not in log
    assert (
        "--set-secrets=USER_ANALYTICS_DB_PASSWORD="
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD:latest" in log
    )
    assert (
        "--set-secrets=MODAL_TOKEN_ID="
        "household-api-staging-MODAL_TOKEN_ID:latest,"
        "MODAL_TOKEN_SECRET=household-api-staging-MODAL_TOKEN_SECRET:latest"
        in log
    )
    assert "gcloud secrets versions add" in log
    assert "add-iam-policy-binding" not in log
    assert "analytics@password,with,comma" not in log
    assert "modal-token,secret@example" not in log
    assert "gcloud storage cp" in log
    assert "gs://manifest-bucket/staging/failover-manifest.json" in log
    assert "gcloud run deploy household-api-staging-gateway" in log
    assert "HOUSEHOLD_MODAL_CANARY_APP_NAME: |-" in log
    assert "  household-canary" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_CANARY_FUNCTION_NAME: |-" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_CANARY_TIMEOUT_SECONDS: |-" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_FAILURE_MIN_COUNT: |-" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_FAILURE_RATE: |-" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_FAILURE_WINDOW_SECONDS: |-" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_MIN_OPEN_SECONDS: |-" in log
    assert "HOUSEHOLD_FAILOVER_MODAL_RECOVERY_SUCCESSES: |-" in log
    assert "HOUSEHOLD_FAILOVER_CLOUD_RUN_WORKER_TIMEOUT_SECONDS: |-" in log
    assert "  900" in log
    assert "--allow-unauthenticated --min-instances 1" in log
    assert "--concurrency 32" in log
    assert (
        "--service-account "
        "household-api-worker@policyengine-test.iam.gserviceaccount.com" in log
    )
    assert (
        "--service-account "
        "household-api-gateway@policyengine-test.iam.gserviceaccount.com"
        in log
    )
    assert "123456789-compute@developer.gserviceaccount.com" not in log
    assert "gateway_url=https://household-api-staging-gateway.run.app" in (
        output_path.read_text()
    )


def test_cloud_run_deploy_failover_requires_manifest_bucket(tmp_path):
    log_path = tmp_path / "commands.log"
    _write_fake_gcloud(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
    }
    env.pop("HOUSEHOLD_FAILOVER_MANIFEST_BUCKET", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-failover.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET" in result.stdout


def test_cloud_run_deploy_failover_requires_service_accounts(tmp_path):
    log_path = tmp_path / "commands.log"
    _write_fake_gcloud(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET": "manifest-bucket",
        "MODAL_TOKEN_ID": "modal-token-id",
        "MODAL_TOKEN_SECRET": "modal-token-secret",
    }
    env.pop("HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT", None)
    env.pop("HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-failover.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT" in result.stdout
    assert "HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT" in result.stdout


def test_cloud_run_deploy_failover_requires_modal_credentials(tmp_path):
    log_path = tmp_path / "commands.log"
    _write_fake_gcloud(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET": "manifest-bucket",
    }
    env.pop("MODAL_TOKEN_ID", None)
    env.pop("MODAL_TOKEN_SECRET", None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-failover.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "MODAL_TOKEN_ID" in result.stdout
    assert "MODAL_TOKEN_SECRET" in result.stdout
    assert not log_path.exists()


def test_cloud_run_deploy_failover_handles_empty_optional_secret_args(
    tmp_path,
):
    log_path = tmp_path / "commands.log"
    output_path = tmp_path / "github-output.txt"
    _write_fake_uv(tmp_path, log_path)
    _write_fake_docker(tmp_path, log_path)
    _write_fake_gcloud(tmp_path, log_path)
    _write_fake_curl(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "UV_BIN": str(tmp_path / "uv"),
        "DOCKER_BIN": str(tmp_path / "docker"),
        "GCLOUD_BIN": str(tmp_path / "gcloud"),
        "CURL_BIN": str(tmp_path / "curl"),
        "GITHUB_OUTPUT": str(output_path),
        "GITHUB_SHA": "abc123",
        "MODAL_ENVIRONMENT": "staging",
        "GOOGLE_CLOUD_PROJECT": "policyengine-test",
        "HOUSEHOLD_FAILOVER_MANIFEST_BUCKET": "manifest-bucket",
        "MODAL_TOKEN_ID": "modal-token-id@example",
        "MODAL_TOKEN_SECRET": "modal-token,secret@example",
        "HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT": (
            "household-api-gateway@policyengine-test.iam.gserviceaccount.com"
        ),
        "HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT": (
            "household-api-worker@policyengine-test.iam.gserviceaccount.com"
        ),
    }
    for key in ("USER_ANALYTICS_DB_PASSWORD",):
        env.pop(key, None)

    result = subprocess.run(
        ["bash", ".github/scripts/cloud-run-deploy-failover.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text()
    assert "gcloud run deploy household-api-staging-current-worker" in log
    assert "gcloud run deploy household-api-staging-gateway" in log
    assert (
        "--set-secrets=MODAL_TOKEN_ID="
        "household-api-staging-MODAL_TOKEN_ID:latest,"
        "MODAL_TOKEN_SECRET=household-api-staging-MODAL_TOKEN_SECRET:latest"
        in log
    )
    assert "modal-token,secret@example" not in log
    assert "gateway_url=https://household-api-staging-gateway.run.app" in (
        output_path.read_text()
    )


def _write_fake_uv(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "uv"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv $*" >> "{log_path}"

output_tsv=""
manifest_output=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --output-tsv)
      shift
      output_tsv="$1"
      ;;
    --manifest-output)
      shift
      manifest_output="$1"
      ;;
  esac
  shift || true
done

if [[ -n "${{output_tsv}}" ]]; then
  cat > "${{output_tsv}}" <<'EOF'
current	modal-current	{{"uk":"2.31.0","us":"1.0.0"}}
frontier	modal-frontier	{{"uk":"2.88.18","us":"2.0.0"}}
EOF
fi

if [[ -n "${{manifest_output}}" ]]; then
  printf '{{"schema_version":1}}\\n' > "${{manifest_output}}"
fi
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


def _write_fake_curl(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "curl"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "curl $*" >> "{log_path}"
"""
    )
    script.chmod(0o755)
