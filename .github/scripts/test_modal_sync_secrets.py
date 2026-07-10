import json
import os
from pathlib import Path
import subprocess


def test_modal_sync_secrets_passes_minimal_observability_env(tmp_path):
    log_path = tmp_path / "uv.log"
    secret_json = tmp_path / "secret.json"
    _write_fake_uv(tmp_path, log_path)

    env = {
        # Strip inherited observability vars so the assertions below see
        # exactly the values this test sets, not developer-shell state.
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OBSERVABILITY_")
        },
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_SECRET_JSON": str(secret_json),
        "MODAL_ENVIRONMENT": "staging",
        "APP__ENVIRONMENT": "staging",
        "AUTH0_ADDRESS_NO_DOMAIN": "auth.example.com",
        "AUTH0_AUDIENCE_NO_DOMAIN": "api.example.com",
        "GCP_CREDENTIALS_JSON": "{}",
        "GOOGLE_CLOUD_PROJECT": "policyengine-household-api",
        "ANALYTICS__ENABLED": "false",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics-password",
        "ANALYTICS__CLOUD_TASKS__PROJECT": "policyengine-test",
        "ANALYTICS__CLOUD_TASKS__LOCATION": "us-central1",
        "ANALYTICS__CLOUD_TASKS__QUEUE": "analytics-writes",
        "ANALYTICS__CLOUD_TASKS__TARGET_URL": (
            "https://writer.run.app/internal/analytics/calculate/write"
        ),
        "ANALYTICS__CLOUD_TASKS__SERVICE_ACCOUNT_EMAIL": (
            "tasks@policyengine-test.iam.gserviceaccount.com"
        ),
        "ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE": "https://writer.run.app",
        "OBSERVABILITY_ENABLED": "true",
        "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME": "household-logs",
        "OBSERVABILITY_GOOGLE_SERVICE_ACCOUNT_EMAIL": (
            "observability-writer@policyengine-observability."
            "iam.gserviceaccount.com"
        ),
        "OBSERVABILITY_GOOGLE_WORKLOAD_IDENTITY_PROVIDER": (
            "projects/790230211054/locations/global/"
            "workloadIdentityPools/modal/providers/modal"
        ),
        "OBSERVABILITY_LOG_DESTINATIONS": "google_cloud_logging",
        "OBSERVABILITY_LOG_PROFILE": "gcp-direct",
        "OBSERVABILITY_LOG_QUEUE_MAXSIZE": "500",
        "OBSERVABILITY_LOG_QUEUE_CLOSE_TIMEOUT_SECONDS": "1.5",
        "OBSERVABILITY_GOOGLE_WRITE_TIMEOUT_SECONDS": "5",
        "OBSERVABILITY_LOG_RAW_IP": "false",
        "OBSERVABILITY_METRIC_ATTRIBUTE_KEYS": "ignored",
        "OBSERVABILITY_REQUEST_LOGS_ENABLED": "true",
        "OTEL_ENABLED": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.com",
        "OTEL_EXPORTER_OTLP_HEADERS": "api-key=secret",
        "OTEL_EXPORTER_OTLP_INSECURE": "false",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_SERVICE_NAME": "ignored",
    }

    result = subprocess.run(
        ["bash", ".github/scripts/modal-sync-secrets.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(secret_json.read_text())
    assert payload["MODAL_ENVIRONMENT"] == "staging"
    assert payload["OBSERVABILITY_ENVIRONMENT"] == "staging"
    assert payload["OBSERVABILITY_PLATFORM"] == "modal"
    # GOOGLE_CLOUD_PROJECT is set to the runtime project above, but the
    # log sink must fall back to the fixed dedicated project, not drift
    # with the runtime.
    assert (
        payload["OBSERVABILITY_GOOGLE_CLOUD_PROJECT"]
        == "policyengine-observability"
    )
    assert payload["OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME"] == "household-logs"
    assert payload["OBSERVABILITY_LOG_DESTINATIONS"] == "google_cloud_logging"
    assert payload["OBSERVABILITY_LOG_PROFILE"] == "gcp-direct"
    assert payload["OBSERVABILITY_LOG_QUEUE_MAXSIZE"] == "500"
    assert payload["OBSERVABILITY_LOG_QUEUE_CLOSE_TIMEOUT_SECONDS"] == "1.5"
    assert payload["OBSERVABILITY_GOOGLE_WRITE_TIMEOUT_SECONDS"] == "5"
    assert (
        payload["OBSERVABILITY_GOOGLE_SERVICE_ACCOUNT_EMAIL"]
        == "observability-writer@policyengine-observability."
        "iam.gserviceaccount.com"
    )
    assert payload["OBSERVABILITY_GOOGLE_WORKLOAD_IDENTITY_PROVIDER"] == (
        "projects/790230211054/locations/global/"
        "workloadIdentityPools/modal/providers/modal"
    )
    assert payload["OBSERVABILITY_ENABLED"] == "true"
    assert payload["OBSERVABILITY_LOG_RAW_IP"] == "false"
    assert payload["OBSERVABILITY_REQUEST_LOGS_ENABLED"] == "true"
    assert payload["ANALYTICS__ENABLED"] == "false"
    assert "USER_ANALYTICS_DB_CONNECTION_NAME" not in payload
    assert "USER_ANALYTICS_DB_USERNAME" not in payload
    assert "USER_ANALYTICS_DB_PASSWORD" not in payload
    assert "ANALYTICS__CLOUD_TASKS__QUEUE" not in payload
    assert "ANALYTICS__CLOUD_TASKS__TARGET_URL" not in payload
    assert "OBSERVABILITY_METRIC_ATTRIBUTE_KEYS" not in payload
    assert "OTEL_ENABLED" not in payload
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in payload
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in payload
    assert "OTEL_EXPORTER_OTLP_INSECURE" not in payload
    assert "OTEL_EXPORTER_OTLP_PROTOCOL" not in payload
    assert "OTEL_SERVICE_NAME" not in payload
    assert "modal secret create household-api --env staging" in (
        log_path.read_text()
    )


def test_modal_sync_secrets_includes_cloud_tasks_analytics_config(tmp_path):
    log_path = tmp_path / "uv.log"
    secret_json = tmp_path / "secret.json"
    _write_fake_uv(tmp_path, log_path)

    env = {
        # Strip inherited observability vars: this scenario also pins
        # that unset knobs stay out of the secret (package defaults
        # govern unless deliberately overridden).
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OBSERVABILITY_")
        },
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_SECRET_JSON": str(secret_json),
        "MODAL_ENVIRONMENT": "staging",
        "APP__ENVIRONMENT": "staging",
        "AUTH0_ADDRESS_NO_DOMAIN": "auth.example.com",
        "AUTH0_AUDIENCE_NO_DOMAIN": "api.example.com",
        "GCP_CREDENTIALS_JSON": "{}",
        "ANALYTICS__ENABLED": "true",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics-password",
        "ANALYTICS__CLOUD_TASKS__PROJECT": "policyengine-test",
        "ANALYTICS__CLOUD_TASKS__LOCATION": "us-central1",
        "ANALYTICS__CLOUD_TASKS__QUEUE": "analytics-writes",
        "ANALYTICS__CLOUD_TASKS__TARGET_URL": (
            "https://writer.run.app/internal/analytics/calculate/write"
        ),
        "ANALYTICS__CLOUD_TASKS__SERVICE_ACCOUNT_EMAIL": (
            "tasks@policyengine-test.iam.gserviceaccount.com"
        ),
        "ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE": "https://writer.run.app",
    }

    result = subprocess.run(
        ["bash", ".github/scripts/modal-sync-secrets.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(secret_json.read_text())
    assert payload["ANALYTICS__CLOUD_TASKS__QUEUE"] == "analytics-writes"
    assert payload["ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE"] == (
        "https://writer.run.app"
    )
    # Unset observability knobs must be omitted so the package's clamped
    # defaults govern at runtime.
    assert "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME" not in payload
    assert "OBSERVABILITY_LOG_DESTINATIONS" not in payload
    assert "OBSERVABILITY_LOG_PROFILE" not in payload
    assert "OBSERVABILITY_LOG_QUEUE_MAXSIZE" not in payload
    assert "OBSERVABILITY_LOG_QUEUE_CLOSE_TIMEOUT_SECONDS" not in payload
    assert "OBSERVABILITY_GOOGLE_WRITE_TIMEOUT_SECONDS" not in payload


def test_modal_sync_secrets_requires_cloud_tasks_analytics_config(tmp_path):
    log_path = tmp_path / "uv.log"
    secret_json = tmp_path / "secret.json"
    _write_fake_uv(tmp_path, log_path)

    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MODAL_SECRET_JSON": str(secret_json),
        "MODAL_ENVIRONMENT": "staging",
        "APP__ENVIRONMENT": "staging",
        "AUTH0_ADDRESS_NO_DOMAIN": "auth.example.com",
        "AUTH0_AUDIENCE_NO_DOMAIN": "api.example.com",
        "GCP_CREDENTIALS_JSON": "{}",
        "ANALYTICS__ENABLED": "true",
        "USER_ANALYTICS_DB_CONNECTION_NAME": "project:region:db",
        "USER_ANALYTICS_DB_USERNAME": "analytics-user",
        "USER_ANALYTICS_DB_PASSWORD": "analytics-password",
    }

    result = subprocess.run(
        ["bash", ".github/scripts/modal-sync-secrets.sh"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "ANALYTICS__CLOUD_TASKS__QUEUE" in result.stderr
    assert not secret_json.exists()


def _write_fake_uv(tmp_path: Path, log_path: Path) -> None:
    script = tmp_path / "uv"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "uv $*" >> "{log_path}"

json_file=""
while [[ "$#" -gt 0 ]]; do
  if [[ "$1" == "--from-json" ]]; then
    shift
    json_file="$1"
  fi
  shift || true
done

if [[ -n "${{json_file}}" ]]; then
  cp "${{json_file}}" "${{MODAL_SECRET_JSON}}"
fi
"""
    )
    script.chmod(0o755)
