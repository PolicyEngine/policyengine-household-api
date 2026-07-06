#!/usr/bin/env bash
set -euo pipefail

channels_script="${CLOUD_RUN_CHANNELS_SCRIPT:-.github/scripts/cloud_run_failover_channels.py}"
scaling_controls_script="${CLOUD_RUN_SCALING_CONTROLS_SCRIPT:-.github/scripts/cloud_run_apply_scaling_controls.py}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cloud-run-deploy-lib.sh
source "${script_dir}/cloud-run-deploy-lib.sh"

apply_worker_scaling_controls() {
  local service="${1:?service is required}"
  local scaling_concurrency_target="${2:-}"
  local service_yaml

  if [ -z "${scaling_concurrency_target}" ] ||
    [ "${scaling_concurrency_target}" = "none" ]; then
    return
  fi

  service_yaml="$(mktemp)"
  "${gcloud_bin}" run services describe "${service}" \
    --region "${region}" \
    --project "${project}" \
    --format export > "${service_yaml}"
  "${uv_bin}" run python "${scaling_controls_script}" \
    --input-yaml "${service_yaml}" \
    --output-yaml "${service_yaml}" \
    --scaling-concurrency-target "${scaling_concurrency_target}"
  "${gcloud_bin}" run services replace "${service_yaml}" \
    --region "${region}" \
    --project "${project}" \
    --quiet
  rm -f "${service_yaml}"
}

require_env \
  MODAL_ENVIRONMENT \
  GOOGLE_CLOUD_PROJECT \
  HOUSEHOLD_FAILOVER_MANIFEST_BUCKET \
  MODAL_TOKEN_ID \
  MODAL_TOKEN_SECRET \
  HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT \
  HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT

if is_truthy "${ANALYTICS__ENABLED:-false}"; then
  # The analytics writer deploys in its own job before this script runs; the
  # workflow passes the deployed writer URL in so workers can enqueue to it.
  require_env HOUSEHOLD_ANALYTICS_WRITER_URL
fi

project="${GOOGLE_CLOUD_PROJECT}"
region="${HOUSEHOLD_CLOUD_RUN_REGION:-us-central1}"
repository="${HOUSEHOLD_CLOUD_RUN_ARTIFACT_REPOSITORY:-household-api}"
environment="$(cloud_run_environment)"
service_prefix="${HOUSEHOLD_CLOUD_RUN_SERVICE_PREFIX:-household-api-${environment}}"
secret_prefix="${HOUSEHOLD_CLOUD_RUN_SECRET_PREFIX:-${service_prefix}}"
manifest_bucket="${HOUSEHOLD_FAILOVER_MANIFEST_BUCKET}"
manifest_blob="${HOUSEHOLD_FAILOVER_MANIFEST_BLOB:-${environment}/failover-manifest.json}"
artifact_host="${region}-docker.pkg.dev"
image_tag="${GITHUB_SHA:-local}"
image_base="${artifact_host}/${project}/${repository}"

# Runtime service accounts are required (validated above); never silently fall
# back to the broad Compute Engine default service account for a public deploy.
gateway_service_account="${HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT}"
worker_service_account="${HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT}"

gateway_service="${HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE:-$(service_name gateway)}"
gateway_image="${image_base}/${gateway_service}:${image_tag}"
gateway_min_instances="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MIN_INSTANCES:-1}"
gateway_max_instances="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MAX_INSTANCES:-20}"
gateway_concurrency="${HOUSEHOLD_CLOUD_RUN_GATEWAY_CONCURRENCY:-32}"
gateway_timeout="${HOUSEHOLD_CLOUD_RUN_GATEWAY_TIMEOUT_SECONDS:-1200}"
gateway_cpu="${HOUSEHOLD_CLOUD_RUN_GATEWAY_CPU:-1}"
gateway_memory="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MEMORY:-512Mi}"
gateway_ingress="${HOUSEHOLD_CLOUD_RUN_GATEWAY_INGRESS:-}"
gateway_public_url="${HOUSEHOLD_CLOUD_RUN_GATEWAY_PUBLIC_URL:-}"
gateway_probe_period_seconds="${HOUSEHOLD_CLOUD_RUN_GATEWAY_PROBE_PERIOD_SECONDS:-2}"
gateway_probe_timeout_seconds="${HOUSEHOLD_CLOUD_RUN_GATEWAY_PROBE_TIMEOUT_SECONDS:-2}"
gateway_probe_failure_threshold="${HOUSEHOLD_CLOUD_RUN_GATEWAY_PROBE_FAILURE_THRESHOLD:-30}"

worker_min_instances="${HOUSEHOLD_CLOUD_RUN_WORKER_MIN_INSTANCES:-0}"
worker_max_instances="${HOUSEHOLD_CLOUD_RUN_WORKER_MAX_INSTANCES:-100}"
worker_concurrency="${HOUSEHOLD_CLOUD_RUN_WORKER_CONCURRENCY:-5}"
worker_threads="${HOUSEHOLD_CLOUD_RUN_WORKER_THREADS:-${worker_concurrency}}"
worker_timeout="${HOUSEHOLD_CLOUD_RUN_WORKER_TIMEOUT_SECONDS:-1200}"
gateway_worker_timeout="${HOUSEHOLD_FAILOVER_CLOUD_RUN_WORKER_TIMEOUT_SECONDS:-900}"
worker_cpu="${HOUSEHOLD_CLOUD_RUN_WORKER_CPU:-1}"
worker_memory="${HOUSEHOLD_CLOUD_RUN_WORKER_MEMORY:-4Gi}"
worker_scaling_concurrency_target="$(
  printf '%s' "${HOUSEHOLD_CLOUD_RUN_WORKER_SCALING_CONCURRENCY_TARGET:-0.3}"
)"
# Workers load snapshotted tax-benefit systems at boot, so their startup
# budget is much larger than the gateway's.
worker_probe_period_seconds="${HOUSEHOLD_CLOUD_RUN_WORKER_PROBE_PERIOD_SECONDS:-5}"
worker_probe_timeout_seconds="${HOUSEHOLD_CLOUD_RUN_WORKER_PROBE_TIMEOUT_SECONDS:-3}"
worker_probe_failure_threshold="${HOUSEHOLD_CLOUD_RUN_WORKER_PROBE_FAILURE_THRESHOLD:-60}"

require_analytics_cloud_tasks_env

analytics_writer_url=""
cloud_tasks_target_url=""
if is_truthy "${ANALYTICS__ENABLED:-false}"; then
  analytics_writer_url="${HOUSEHOLD_ANALYTICS_WRITER_URL%/}"
  analytics_writer_target_url="$(
    printf '%s/internal/analytics/calculate/write' "${analytics_writer_url}"
  )"
  cloud_tasks_target_url="$(
    printf '%s' "${ANALYTICS__CLOUD_TASKS__TARGET_URL:-${analytics_writer_target_url}}"
  )"
fi

channels_tsv="$(mktemp)"
manifest_json="$(mktemp)"
worker_urls_tsv="$(mktemp)"
worker_env_file="$(mktemp)"
worker_secrets_file="$(mktemp)"
gateway_env_file="$(mktemp)"
gateway_secrets_file="$(mktemp)"
trap 'rm -f "${channels_tsv}" "${manifest_json}" "${worker_urls_tsv}" "${worker_env_file}" "${worker_secrets_file}" "${gateway_env_file}" "${gateway_secrets_file}"' EXIT

"${uv_bin}" run python "${channels_script}" \
  --modal-environment "${MODAL_ENVIRONMENT}" \
  --environment "${environment}" \
  --output-tsv "${channels_tsv}"

configure_artifact_registry

while IFS=$'\t' read -r channel modal_app_name package_versions_json; do
  if [ -z "${channel}" ]; then
    continue
  fi

  worker_service="$(service_name worker "${channel}")"
  worker_image="${image_base}/${worker_service}:${image_tag}"

  "${docker_bin}" build \
    --file gcp/cloud_run/worker.Dockerfile \
    --build-arg "HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON=${package_versions_json}" \
    --tag "${worker_image}" \
    .
  "${docker_bin}" push "${worker_image}"

  : > "${worker_env_file}"
  : > "${worker_secrets_file}"
  append_env_value "${worker_env_file}" APP__ENVIRONMENT "${environment}"
  append_observability_env "${worker_env_file}"
  append_env_value "${worker_env_file}" WEB_THREADS "${worker_threads}"
  append_env_value "${worker_env_file}" WEB_TIMEOUT "${worker_timeout}"
  append_env_value "${worker_env_file}" HOUSEHOLD_FAILOVER_CHANNEL "${channel}"
  append_env_value \
    "${worker_env_file}" \
    HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON \
    "${package_versions_json}"
  append_env_if_set "${worker_env_file}" ANALYTICS__ENABLED
  if is_truthy "${ANALYTICS__ENABLED:-false}"; then
    append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_CONNECTION_NAME
    append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_USERNAME
    append_env_if_set "${worker_env_file}" ANALYTICS__CLOUD_TASKS__PROJECT
    append_env_if_set "${worker_env_file}" ANALYTICS__CLOUD_TASKS__LOCATION
    append_env_if_set "${worker_env_file}" ANALYTICS__CLOUD_TASKS__QUEUE
    append_env_value \
      "${worker_env_file}" \
      ANALYTICS__CLOUD_TASKS__TARGET_URL \
      "${cloud_tasks_target_url}"
    append_env_if_set \
      "${worker_env_file}" \
      ANALYTICS__CLOUD_TASKS__SERVICE_ACCOUNT_EMAIL
    if [ -n "${ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE:-}" ]; then
      append_env_value \
        "${worker_env_file}" \
        ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE \
        "${ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE}"
    else
      append_env_value \
        "${worker_env_file}" \
        ANALYTICS__CLOUD_TASKS__OIDC_AUDIENCE \
        "${analytics_writer_url}"
    fi
    append_env_if_set \
      "${worker_env_file}" \
      ANALYTICS__CLOUD_TASKS__DISPATCH_DEADLINE_SECONDS
    sync_secret_if_set \
      "${worker_secrets_file}" \
      USER_ANALYTICS_DB_PASSWORD
  fi
  append_env_if_set "${worker_env_file}" AUTH__ENABLED
  append_env_if_set "${worker_env_file}" AUTH0_ADDRESS_NO_DOMAIN
  append_env_if_set "${worker_env_file}" AUTH0_AUDIENCE_NO_DOMAIN
  worker_env_arg=""
  worker_secret_arg=""
  if worker_env_arg="$(env_args_from_file "${worker_env_file}")"; then
    :
  fi
  if worker_secret_arg="$(secret_args_from_file "${worker_secrets_file}")"; then
    :
  fi

  worker_deploy_cmd=(
    "${gcloud_bin}" run deploy "${worker_service}"
    --image "${worker_image}"
    --region "${region}"
    --project "${project}"
    --platform managed
    --no-allow-unauthenticated
    --min-instances "${worker_min_instances}"
    --max-instances "${worker_max_instances}"
    --concurrency "${worker_concurrency}"
    --timeout "${worker_timeout}"
    --cpu "${worker_cpu}"
    --memory "${worker_memory}"
    --service-account "${worker_service_account}"
  )
  if [ -n "${worker_env_arg}" ]; then
    worker_deploy_cmd+=("${worker_env_arg}")
  fi
  if [ -n "${worker_secret_arg}" ]; then
    worker_deploy_cmd+=("${worker_secret_arg}")
  fi
  worker_deploy_cmd+=(--quiet)

  deploy_run_service "${worker_deploy_cmd[@]}"
  apply_worker_scaling_controls \
    "${worker_service}" \
    "${worker_scaling_concurrency_target}"
  apply_startup_probe \
    "${worker_service}" \
    "${worker_probe_period_seconds}" \
    "${worker_probe_timeout_seconds}" \
    "${worker_probe_failure_threshold}"

  worker_url="$(
    "${gcloud_bin}" run services describe "${worker_service}" \
      --region "${region}" \
      --project "${project}" \
      --format='value(status.url)'
  )"
  printf '%s\t%s\n' "${channel}" "${worker_url}" >> "${worker_urls_tsv}"
  echo "Deployed ${channel} Cloud Run worker for Modal app ${modal_app_name}: ${worker_url}"
done < "${channels_tsv}"

worker_url_args=()
while IFS=$'\t' read -r channel worker_url; do
  if [ -n "${channel}" ]; then
    worker_url_args+=(--worker-url "${channel}=${worker_url}")
  fi
done < "${worker_urls_tsv}"

"${uv_bin}" run python "${channels_script}" \
  --modal-environment "${MODAL_ENVIRONMENT}" \
  --environment "${environment}" \
  --manifest-output "${manifest_json}" \
  "${worker_url_args[@]}"

"${gcloud_bin}" storage cp \
  "${manifest_json}" \
  "gs://${manifest_bucket}/${manifest_blob}" \
  --project "${project}" \
  --content-type application/json

"${docker_bin}" build \
  --file gcp/cloud_run/gateway.Dockerfile \
  --tag "${gateway_image}" \
  .
"${docker_bin}" push "${gateway_image}"

: > "${gateway_env_file}"
: > "${gateway_secrets_file}"
append_env_value "${gateway_env_file}" APP__ENVIRONMENT "${environment}"
append_observability_env "${gateway_env_file}"
append_env_value "${gateway_env_file}" MODAL_ENVIRONMENT "${MODAL_ENVIRONMENT}"
append_env_value \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MANIFEST_BUCKET \
  "${manifest_bucket}"
append_env_value \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MANIFEST_BLOB \
  "${manifest_blob}"
append_env_if_set "${gateway_env_file}" HOUSEHOLD_FAILOVER_FORCE_BACKEND
append_env_if_set "${gateway_env_file}" HOUSEHOLD_FAILOVER_DISABLE_CLOUD_RUN_AUTH
append_env_if_set "${gateway_env_file}" HOUSEHOLD_FAILOVER_MODAL_TIMEOUT_SECONDS
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_REQUEST_TIMEOUT_SECONDS
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_PROBE_TIMEOUT_SECONDS
append_env_if_set "${gateway_env_file}" HOUSEHOLD_MODAL_CANARY_APP_NAME
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_CANARY_FUNCTION_NAME
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_CANARY_TIMEOUT_SECONDS
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_FAILURE_MIN_COUNT
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_FAILURE_RATE
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_FAILURE_WINDOW_SECONDS
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_MIN_OPEN_SECONDS
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_MODAL_RECOVERY_SUCCESSES
append_env_value \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_CLOUD_RUN_WORKER_TIMEOUT_SECONDS \
  "${gateway_worker_timeout}"
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_SLACK_TIMEOUT_SECONDS
append_env_if_set \
  "${gateway_env_file}" \
  HOUSEHOLD_FAILOVER_SLACK_COOLDOWN_SECONDS
sync_secret_if_set \
  "${gateway_secrets_file}" \
  MODAL_TOKEN_ID
sync_secret_if_set \
  "${gateway_secrets_file}" \
  MODAL_TOKEN_SECRET
sync_secret_if_set \
  "${gateway_secrets_file}" \
  HOUSEHOLD_FAILOVER_SLACK_WEBHOOK_URL
gateway_env_arg=""
gateway_secret_arg=""
if gateway_env_arg="$(env_args_from_file "${gateway_env_file}")"; then
  :
fi
if gateway_secret_arg="$(secret_args_from_file "${gateway_secrets_file}")"; then
  :
fi

gateway_deploy_cmd=(
  "${gcloud_bin}" run deploy "${gateway_service}"
  --image "${gateway_image}"
  --region "${region}"
  --project "${project}"
  --platform managed
  --allow-unauthenticated
  --min-instances "${gateway_min_instances}"
  --max-instances "${gateway_max_instances}"
  --concurrency "${gateway_concurrency}"
  --timeout "${gateway_timeout}"
  --cpu "${gateway_cpu}"
  --memory "${gateway_memory}"
  --service-account "${gateway_service_account}"
)
if [ -n "${gateway_ingress}" ]; then
  gateway_deploy_cmd+=(--ingress "${gateway_ingress}")
fi
if [ -n "${gateway_env_arg}" ]; then
  gateway_deploy_cmd+=("${gateway_env_arg}")
fi
if [ -n "${gateway_secret_arg}" ]; then
  gateway_deploy_cmd+=("${gateway_secret_arg}")
fi
gateway_deploy_cmd+=(--quiet)

deploy_run_service "${gateway_deploy_cmd[@]}"

apply_startup_probe \
  "${gateway_service}" \
  "${gateway_probe_period_seconds}" \
  "${gateway_probe_timeout_seconds}" \
  "${gateway_probe_failure_threshold}"

gateway_url="$(
  "${gcloud_bin}" run services describe "${gateway_service}" \
    --region "${region}" \
    --project "${project}" \
    --format='value(status.url)'
)"
gateway_check_url="${gateway_public_url:-${gateway_url}}"
gateway_check_url="${gateway_check_url%/}"

"${curl_bin}" -fsS "${gateway_check_url}/liveness_check"
github_output "gateway_url" "${gateway_check_url}"
github_output "manifest_uri" "gs://${manifest_bucket}/${manifest_blob}"

echo "Cloud Run failover gateway deployed: ${gateway_url}"
if [ "${gateway_check_url}" != "${gateway_url}" ]; then
  echo "Cloud Run failover gateway public URL: ${gateway_check_url}"
fi
