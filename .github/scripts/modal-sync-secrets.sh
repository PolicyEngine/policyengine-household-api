#!/usr/bin/env bash
set -euo pipefail

environment="${MODAL_ENVIRONMENT:-main}"
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
    "USER_ANALYTICS_DB_CONNECTION_NAME",
    "USER_ANALYTICS_DB_USERNAME",
    "USER_ANALYTICS_DB_PASSWORD",
]

if os.getenv("ANALYTICS__ENABLED", "true").lower() not in {"0", "false", "no"}:
    required.extend(
        [
            "USER_ANALYTICS_DB_CONNECTION_NAME",
            "USER_ANALYTICS_DB_USERNAME",
            "USER_ANALYTICS_DB_PASSWORD",
        ]
    )
    optional = [
        key
        for key in optional
        if key
        not in {
            "USER_ANALYTICS_DB_CONNECTION_NAME",
            "USER_ANALYTICS_DB_USERNAME",
            "USER_ANALYTICS_DB_PASSWORD",
        }
    ]

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
