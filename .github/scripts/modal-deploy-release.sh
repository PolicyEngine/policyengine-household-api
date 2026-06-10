#!/usr/bin/env bash
set -euo pipefail

config_json="${1:?Usage: modal-deploy-release.sh CONFIG_JSON [DEPLOY_MODE]}"
deploy_mode="${2:-release}"
output_file="${GITHUB_OUTPUT:-}"
modal_extract_versions_script="${MODAL_EXTRACT_VERSIONS_SCRIPT:-.github/scripts/modal_extract_versions.py}"
modal_sync_secrets_script="${MODAL_SYNC_SECRETS_SCRIPT:-.github/scripts/modal-sync-secrets.sh}"
modal_active_worker_apps_script="${MODAL_ACTIVE_WORKER_APPS_SCRIPT:-.github/scripts/modal_active_worker_apps.py}"
modal_require_active_channels_script="${MODAL_REQUIRE_ACTIVE_CHANNELS_SCRIPT:-.github/scripts/modal_require_active_channels.py}"
modal_cleanup_apps_script="${MODAL_CLEANUP_APPS_SCRIPT:-.github/scripts/modal-cleanup-apps.sh}"
modal_get_url_script="${MODAL_GET_URL_SCRIPT:-.github/scripts/modal-get-url.sh}"

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

deploy_worker_app() {
  local app_name="${1:?app name is required}"
  local package_versions_json="${2:-}"

  HOUSEHOLD_MODAL_WORKER_APP_NAME="${app_name}" \
    HOUSEHOLD_MODAL_PACKAGE_VERSIONS_JSON="${package_versions_json}" \
    MODAL_ENVIRONMENT="${modal_environment}" \
    uv run modal deploy \
      --env "${modal_environment}" \
      -m policyengine_household_api.modal_release.worker_app
}

deploy_canary_app() {
  MODAL_ENVIRONMENT="${modal_environment}" \
    uv run modal deploy \
      --env "${modal_environment}" \
      -m policyengine_household_api.modal_release.canary_app
}

require_env \
  MODAL_ENVIRONMENT \
  USER_ANALYTICS_DB_USERNAME \
  USER_ANALYTICS_DB_PASSWORD \
  USER_ANALYTICS_DB_CONNECTION_NAME

modal_environment="${MODAL_ENVIRONMENT}"

case "${deploy_mode}" in
  code|release)
    ;;
  *)
    echo "::error::Unsupported Modal deploy mode: ${deploy_mode}"
    exit 1
    ;;
esac

uv run python "${modal_require_active_channels_script}" \
  --modal-environment "${modal_environment}"

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
uv run python "${modal_extract_versions_script}" \
  --github-output "${versions_output}"
if [ -n "${output_file}" ]; then
  cat "${versions_output}" >> "${output_file}"
fi
worker_app_name="$(
  awk -F= '$1 == "worker_app_name" {print substr($0, index($0, "=") + 1)}' \
    "${versions_output}"
)"

bash "${modal_sync_secrets_script}"
deploy_canary_app

if [ "${deploy_mode}" = "code" ]; then
  active_apps_tsv="$(mktemp)"
  trap 'rm -f "${versions_output}" "${active_apps_tsv}"' EXIT

  uv run python "${modal_active_worker_apps_script}" \
    --modal-environment "${modal_environment}" \
    --output-tsv "${active_apps_tsv}"

  while IFS=$'\t' read -r active_app_name package_versions_json; do
    if [ -z "${active_app_name}" ]; then
      continue
    fi
    deploy_worker_app "${active_app_name}" "${package_versions_json}"
  done < "${active_apps_tsv}"
else
  new_app_target="$(config_value new_app_target)"
  if [ "${new_app_target}" != "none" ]; then
    deploy_worker_app "${worker_app_name}" ""
  fi

  uv run python -m policyengine_household_api.modal_release.update_manifest \
    --config-json "${config_json}" \
    --new-app-name "${worker_app_name}" \
    --analytics-database-revision "${analytics_database_revision}" \
    --modal-environment "${modal_environment}" \
    --cleanup-output modal-cleanup.json \
    --manifest-output modal-manifest.json
fi

uv run modal deploy \
  --env "${modal_environment}" \
  -m policyengine_household_api.modal_release.gateway_app

if [ "${deploy_mode}" = "release" ]; then
  cleanup_target="$(config_value cleanup_target)"
  if [ "${cleanup_target}" != "none" ]; then
    bash "${modal_cleanup_apps_script}" modal-cleanup.json
  fi
fi

gateway_url="$(bash "${modal_get_url_script}")"
curl -fsS "${gateway_url}/liveness_check"
