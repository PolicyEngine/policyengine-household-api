import os
from pathlib import Path
import subprocess


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
        "AUTH__ENABLED": "true",
        "AUTH0_ADDRESS_NO_DOMAIN": "auth.example.com",
        "AUTH0_AUDIENCE_NO_DOMAIN": "api.example.com",
        "ANTHROPIC_API_KEY": "sk-ant@test,secret",
        "ANALYTICS__ENABLED": "true",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics@password,with,comma",
        "HOUSEHOLD_FAILOVER_MODAL_REQUEST_TIMEOUT_SECONDS": "45",
        "HOUSEHOLD_FAILOVER_MODAL_PROBE_TIMEOUT_SECONDS": "5",
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
    assert "--concurrency 25" in log
    assert "--env-vars-file=" in log
    assert "--set-env-vars" not in log
    assert (
        "--set-secrets=USER_ANALYTICS_DB_PASSWORD="
        "household-api-staging-USER_ANALYTICS_DB_PASSWORD:latest,"
        "ANTHROPIC_API_KEY=household-api-staging-ANTHROPIC_API_KEY:latest"
        in log
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
    assert "sk-ant@test,secret" not in log
    assert "gcloud storage cp" in log
    assert "gs://manifest-bucket/staging/failover-manifest.json" in log
    assert "gcloud run deploy household-api-staging-gateway" in log
    assert "--allow-unauthenticated --min-instances 1" in log
    assert "--concurrency 32" in log
    assert "--service-account 123456789-compute@developer.gserviceaccount.com" in log
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

if [[ "$*" == "projects describe policyengine-test --format=value(projectNumber)" ]]; then
  echo "123456789"
  exit 0
fi

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
