#!/usr/bin/env bash
set -euo pipefail

# Deploys the Cloud Run analytics writer for one environment. This runs as its
# own deploy job, before either integration-test lane starts, so tests that
# assert analytics rows never race the writer deploy.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cloud-run-deploy-lib.sh
source "${script_dir}/cloud-run-deploy-lib.sh"

require_env \
  MODAL_ENVIRONMENT \
  GOOGLE_CLOUD_PROJECT

if ! is_truthy "${ANALYTICS__ENABLED:-false}"; then
  echo "Analytics is disabled; skipping Cloud Run analytics writer deploy."
  exit 0
fi

require_env HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT

project="${GOOGLE_CLOUD_PROJECT}"
region="${HOUSEHOLD_CLOUD_RUN_REGION:-us-central1}"
repository="${HOUSEHOLD_CLOUD_RUN_ARTIFACT_REPOSITORY:-household-api}"
environment="$(cloud_run_environment)"
service_prefix="${HOUSEHOLD_CLOUD_RUN_SERVICE_PREFIX:-household-api-${environment}}"
secret_prefix="${HOUSEHOLD_CLOUD_RUN_SECRET_PREFIX:-${service_prefix}}"
artifact_host="${region}-docker.pkg.dev"
image_tag="${GITHUB_SHA:-local}"
image_base="${artifact_host}/${project}/${repository}"

analytics_writer_service_account="${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE_ACCOUNT}"
analytics_writer_service="$(
  printf '%s' \
    "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_SERVICE:-$(service_name analytics-writer)}"
)"
analytics_writer_image="${image_base}/${analytics_writer_service}:${image_tag}"
analytics_writer_min_instances="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_MIN_INSTANCES:-0}"
)"
analytics_writer_max_instances="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_MAX_INSTANCES:-20}"
)"
analytics_writer_concurrency="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_CONCURRENCY:-20}"
)"
analytics_writer_threads="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_THREADS:-8}"
)"
analytics_writer_timeout="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_TIMEOUT_SECONDS:-300}"
)"
analytics_writer_cpu="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_CPU:-1}"
)"
analytics_writer_memory="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_MEMORY:-512Mi}"
)"
analytics_writer_ingress="${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_INGRESS:-}"
analytics_writer_probe_period_seconds="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_PROBE_PERIOD_SECONDS:-2}"
)"
analytics_writer_probe_timeout_seconds="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_PROBE_TIMEOUT_SECONDS:-2}"
)"
analytics_writer_probe_failure_threshold="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_ANALYTICS_WRITER_PROBE_FAILURE_THRESHOLD:-30}"
)"

analytics_writer_env_file="$(mktemp)"
analytics_writer_secrets_file="$(mktemp)"
trap 'rm -f "${analytics_writer_env_file}" "${analytics_writer_secrets_file}"' EXIT

configure_artifact_registry

"${docker_bin}" build \
  --file gcp/cloud_run/analytics_writer.Dockerfile \
  --tag "${analytics_writer_image}" \
  .
"${docker_bin}" push "${analytics_writer_image}"

: > "${analytics_writer_env_file}"
: > "${analytics_writer_secrets_file}"
append_env_value "${analytics_writer_env_file}" APP__ENVIRONMENT "${environment}"
append_observability_env "${analytics_writer_env_file}"
append_env_value \
  "${analytics_writer_env_file}" \
  WEB_THREADS \
  "${analytics_writer_threads}"
append_env_value \
  "${analytics_writer_env_file}" \
  WEB_TIMEOUT \
  "${analytics_writer_timeout}"
append_env_if_set "${analytics_writer_env_file}" ANALYTICS__ENABLED
append_env_if_set "${analytics_writer_env_file}" USER_ANALYTICS_DB_CONNECTION_NAME
append_env_if_set "${analytics_writer_env_file}" USER_ANALYTICS_DB_USERNAME
sync_secret_if_set \
  "${analytics_writer_secrets_file}" \
  USER_ANALYTICS_DB_PASSWORD
analytics_writer_env_arg=""
analytics_writer_secret_arg=""
if analytics_writer_env_arg="$(
  env_args_from_file "${analytics_writer_env_file}"
)"; then
  :
fi
if analytics_writer_secret_arg="$(
  secret_args_from_file "${analytics_writer_secrets_file}"
)"; then
  :
fi

analytics_writer_deploy_cmd=(
  "${gcloud_bin}" run deploy "${analytics_writer_service}"
  --image "${analytics_writer_image}"
  --region "${region}"
  --project "${project}"
  --platform managed
  --no-allow-unauthenticated
  --min-instances "${analytics_writer_min_instances}"
  --max-instances "${analytics_writer_max_instances}"
  --concurrency "${analytics_writer_concurrency}"
  --timeout "${analytics_writer_timeout}"
  --cpu "${analytics_writer_cpu}"
  --memory "${analytics_writer_memory}"
  --service-account "${analytics_writer_service_account}"
)
if [ -n "${analytics_writer_env_arg}" ]; then
  analytics_writer_deploy_cmd+=("${analytics_writer_env_arg}")
fi
if [ -n "${analytics_writer_secret_arg}" ]; then
  analytics_writer_deploy_cmd+=("${analytics_writer_secret_arg}")
fi
if [ -n "${analytics_writer_ingress}" ]; then
  analytics_writer_deploy_cmd+=(--ingress "${analytics_writer_ingress}")
fi
analytics_writer_deploy_cmd+=(--quiet)

deploy_run_service "${analytics_writer_deploy_cmd[@]}"

apply_startup_probe \
  "${analytics_writer_service}" \
  "${analytics_writer_probe_period_seconds}" \
  "${analytics_writer_probe_timeout_seconds}" \
  "${analytics_writer_probe_failure_threshold}"

analytics_writer_url="$(
  "${gcloud_bin}" run services describe "${analytics_writer_service}" \
    --region "${region}" \
    --project "${project}" \
    --format='value(status.url)'
)"
github_output "analytics_writer_url" "${analytics_writer_url}"
echo "Deployed Cloud Run analytics writer: ${analytics_writer_url}"
