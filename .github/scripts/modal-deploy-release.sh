#!/usr/bin/env bash
set -euo pipefail

config_json="${1:?Usage: modal-deploy-release.sh CONFIG_JSON}"
modal_environment="${MODAL_ENVIRONMENT:-main}"
output_file="${GITHUB_OUTPUT:-}"

require_env() {
  local missing=()
  for key in "$@"; do
    if [ -z "${!key:-}" ]; then
      missing+=("$key")
    fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "::error::Missing required environment variable(s): ${missing[*]}"
    exit 1
  fi
}

config_value() {
  CONFIG_JSON="${config_json}" python -c '
import json
import os
import sys

config = json.loads(os.environ["CONFIG_JSON"])
print(config.get(sys.argv[1], ""))
' "$1"
}

github_output() {
  if [ -n "${output_file}" ]; then
    printf '%s=%s\n' "$1" "$2" >> "${output_file}"
  fi
}

require_env \
  USER_ANALYTICS_DB_USERNAME \
  USER_ANALYTICS_DB_PASSWORD \
  USER_ANALYTICS_DB_CONNECTION_NAME

uv run alembic upgrade head
analytics_database_revision="$(
  uv run python -m policyengine_household_api.modal_release.analytics_revision
)"
if [ -z "${analytics_database_revision}" ]; then
  echo "::error::Could not determine analytics database Alembic revision after upgrade."
  exit 1
fi
github_output "analytics_database_revision" "${analytics_database_revision}"

versions_output="$(mktemp)"
trap 'rm -f "${versions_output}"' EXIT
uv run python .github/scripts/modal_extract_versions.py \
  --github-output "${versions_output}"
if [ -n "${output_file}" ]; then
  cat "${versions_output}" >> "${output_file}"
fi
worker_app_name="$(
  awk -F= '$1 == "worker_app_name" {print substr($0, index($0, "=") + 1)}' \
    "${versions_output}"
)"

bash .github/scripts/modal-sync-secrets.sh

new_app_target="$(config_value new_app_target)"
if [ "${new_app_target}" != "none" ]; then
  HOUSEHOLD_MODAL_WORKER_APP_NAME="${worker_app_name}" \
    uv run modal deploy \
      --env "${modal_environment}" \
      -m policyengine_household_api.modal_release.worker_app
fi

uv run python -m policyengine_household_api.modal_release.update_manifest \
  --config-json "${config_json}" \
  --new-app-name "${worker_app_name}" \
  --source-commit "${GITHUB_SHA}" \
  --analytics-database-revision "${analytics_database_revision}" \
  --modal-environment "${modal_environment}" \
  --cleanup-output modal-cleanup.json \
  --manifest-output modal-manifest.json

uv run modal deploy \
  --env "${modal_environment}" \
  -m policyengine_household_api.modal_release.gateway_app

cleanup_target="$(config_value cleanup_target)"
if [ "${cleanup_target}" != "none" ]; then
  bash .github/scripts/modal-cleanup-apps.sh modal-cleanup.json
fi

gateway_url="$(bash .github/scripts/modal-get-url.sh)"
github_output "gateway_url" "${gateway_url}"
curl -fsS "${gateway_url}/liveness_check"
