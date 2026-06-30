import json
import os
from pathlib import Path
import subprocess


def test_modal_sync_secrets_passes_minimal_observability_env(tmp_path):
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
        "GOOGLE_CLOUD_PROJECT": "policyengine-household-api",
        "ANALYTICS__ENABLED": "false",
        "OBSERVABILITY_ENABLED": "true",
        "OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME": ("policyengine-observability"),
        "OBSERVABILITY_GOOGLE_SERVICE_ACCOUNT_EMAIL": (
            "observability-writer@policyengine-observability."
            "iam.gserviceaccount.com"
        ),
        "OBSERVABILITY_GOOGLE_WORKLOAD_IDENTITY_PROVIDER": (
            "projects/790230211054/locations/global/"
            "workloadIdentityPools/modal/providers/modal"
        ),
        "OBSERVABILITY_LOG_DESTINATIONS": "google_cloud_logging",
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
    assert (
        payload["OBSERVABILITY_GOOGLE_CLOUD_PROJECT"]
        == "policyengine-observability"
    )
    assert (
        payload["OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME"]
        == "policyengine-observability"
    )
    assert payload["OBSERVABILITY_LOG_DESTINATIONS"] == "google_cloud_logging"
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
