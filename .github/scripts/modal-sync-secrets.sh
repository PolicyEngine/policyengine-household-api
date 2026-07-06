#!/usr/bin/env bash
set -euo pipefail

environment="${MODAL_ENVIRONMENT:-main}"
export MODAL_ENVIRONMENT="${environment}"
secret_name="${HOUSEHOLD_MODAL_SECRET_NAME:-household-api}"
secret_file="$(mktemp)"
trap 'rm -f "${secret_file}"' EXIT

python -c '
import json
import os
import sys
from pathlib import Path

required = [
    "AUTH0_ADDRESS_NO_DOMAIN",
    "AUTH0_AUDIENCE_NO_DOMAIN",
    "GCP_CREDENTIALS_JSON",
]
optional = [
    "OBSERVABILITY_ENABLED",
    "OBSERVABILITY_LOG_RAW_IP",
    "OBSERVABILITY_REQUEST_LOGS_ENABLED",
]
analytics_required = [
    "USER_ANALYTICS_DB_CONNECTION_NAME",
    "USER_ANALYTICS_DB_USERNAME",
    "USER_ANALYTICS_DB_PASSWORD",
    "ANALYTICS__CLOUD_TASKS__PROJECT",
    "ANALYTICS__CLOUD_TASKS__LOCATION",
    "ANALYTICS__CLOUD_TASKS__QUEUE",
    "ANALYTICS__CLOUD_TASKS__TARGET_URL",
    "ANALYTICS__CLOUD_TASKS__SERVICE_ACCOUNT_EMAIL",
    "ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE",
]
analytics_optional = [
    "ANALYTICS__CLOUD_TASKS__DISPATCH_DEADLINE_SECONDS",
]

if os.getenv("ANALYTICS__ENABLED", "true").lower() not in {"0", "false", "no"}:
    required.extend(analytics_required)
    optional.extend(analytics_optional)

missing = [key for key in required if not os.getenv(key)]
if missing:
    raise SystemExit(
        "Missing required Modal secret environment variable(s): "
        + ", ".join(missing)
    )

settings = {
    "APP__ENVIRONMENT": os.getenv("APP__ENVIRONMENT", "production"),
    "AUTH__ENABLED": os.getenv("AUTH__ENABLED", "true"),
    "ANALYTICS__ENABLED": os.getenv("ANALYTICS__ENABLED", "true"),
    "MODAL_ENVIRONMENT": os.getenv("MODAL_ENVIRONMENT", "main"),
    "OBSERVABILITY_ENVIRONMENT": os.getenv(
        "OBSERVABILITY_ENVIRONMENT",
        os.getenv("APP__ENVIRONMENT", "production"),
    ),
    "OBSERVABILITY_PLATFORM": os.getenv("OBSERVABILITY_PLATFORM", "modal"),
}
for key in required + optional:
    value = os.getenv(key)
    if value:
        settings[key] = value

Path(sys.argv[1]).write_text(json.dumps(settings))
' "${secret_file}"

uv run modal secret create "${secret_name}" \
  --env "${environment}" \
  --from-json "${secret_file}" \
  --force
