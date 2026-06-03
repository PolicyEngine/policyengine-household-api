#!/usr/bin/env bash
set -euo pipefail

channels_script="${CLOUD_RUN_CHANNELS_SCRIPT:-.github/scripts/cloud_run_failover_channels.py}"
curl_bin="${CURL_BIN:-curl}"
docker_bin="${DOCKER_BIN:-docker}"
gcloud_bin="${GCLOUD_BIN:-gcloud}"
uv_bin="${UV_BIN:-uv}"
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

cloud_run_environment() {
  if [ -n "${HOUSEHOLD_CLOUD_RUN_ENVIRONMENT:-}" ]; then
    printf '%s\n' "${HOUSEHOLD_CLOUD_RUN_ENVIRONMENT}"
  elif [ "${MODAL_ENVIRONMENT}" = "main" ]; then
    printf '%s\n' "production"
  else
    printf '%s\n' "${MODAL_ENVIRONMENT}"
  fi
}

join_gcloud_env_vars() {
  local joined=""
  local item
  for item in "$@"; do
    if [ -z "${joined}" ]; then
      joined="${item}"
    else
      joined="${joined}@${item}"
    fi
  done
  printf '^@^%s\n' "${joined}"
}

append_env_if_set() {
  local env_file="${1:?env file is required}"
  local key="${2:?env key is required}"
  if [ -n "${!key:-}" ]; then
    printf '%s=%s\n' "${key}" "${!key}" >> "${env_file}"
  fi
}

env_args_from_file() {
  local env_file="${1:?env file is required}"
  local env_values=()
  local line
  if [ ! -s "${env_file}" ]; then
    return
  fi
  while IFS= read -r line; do
    env_values+=("${line}")
  done < "${env_file}"
  printf '%s\n' "--set-env-vars=$(join_gcloud_env_vars "${env_values[@]}")"
}

service_name() {
  local role="${1:?role is required}"
  local channel="${2:-}"
  if [ -n "${channel}" ]; then
    printf '%s-%s-%s\n' "${service_prefix}" "${channel}" "${role}"
  else
    printf '%s-%s\n' "${service_prefix}" "${role}"
  fi
}

github_output() {
  if [ -n "${output_file}" ]; then
    printf '%s=%s\n' "$1" "$2" >> "${output_file}"
  fi
}

deploy_run_service() {
  "$@"
}

require_env \
  MODAL_ENVIRONMENT \
  GOOGLE_CLOUD_PROJECT \
  HOUSEHOLD_FAILOVER_MANIFEST_BUCKET

project="${GOOGLE_CLOUD_PROJECT}"
region="${HOUSEHOLD_CLOUD_RUN_REGION:-us-central1}"
repository="${HOUSEHOLD_CLOUD_RUN_ARTIFACT_REPOSITORY:-household-api}"
environment="$(cloud_run_environment)"
service_prefix="${HOUSEHOLD_CLOUD_RUN_SERVICE_PREFIX:-household-api-${environment}}"
manifest_bucket="${HOUSEHOLD_FAILOVER_MANIFEST_BUCKET}"
manifest_blob="${HOUSEHOLD_FAILOVER_MANIFEST_BLOB:-${environment}/failover-manifest.json}"
artifact_host="${region}-docker.pkg.dev"
image_tag="${GITHUB_SHA:-local}"
image_base="${artifact_host}/${project}/${repository}"

project_number="$(
  "${gcloud_bin}" projects describe "${project}" \
    --format='value(projectNumber)'
)"
gateway_service_account="${HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE_ACCOUNT:-${project_number}-compute@developer.gserviceaccount.com}"
worker_service_account="${HOUSEHOLD_CLOUD_RUN_WORKER_SERVICE_ACCOUNT:-${gateway_service_account}}"

gateway_service="${HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE:-$(service_name gateway)}"
gateway_image="${image_base}/${gateway_service}:${image_tag}"
gateway_min_instances="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MIN_INSTANCES:-1}"
gateway_max_instances="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MAX_INSTANCES:-20}"
gateway_concurrency="${HOUSEHOLD_CLOUD_RUN_GATEWAY_CONCURRENCY:-80}"
gateway_cpu="${HOUSEHOLD_CLOUD_RUN_GATEWAY_CPU:-1}"
gateway_memory="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MEMORY:-512Mi}"

worker_min_instances="${HOUSEHOLD_CLOUD_RUN_WORKER_MIN_INSTANCES:-0}"
worker_max_instances="${HOUSEHOLD_CLOUD_RUN_WORKER_MAX_INSTANCES:-100}"
worker_concurrency="${HOUSEHOLD_CLOUD_RUN_WORKER_CONCURRENCY:-5}"
worker_cpu="${HOUSEHOLD_CLOUD_RUN_WORKER_CPU:-1}"
worker_memory="${HOUSEHOLD_CLOUD_RUN_WORKER_MEMORY:-4Gi}"

channels_tsv="$(mktemp)"
manifest_json="$(mktemp)"
worker_urls_tsv="$(mktemp)"
worker_env_file="$(mktemp)"
gateway_env_file="$(mktemp)"
trap 'rm -f "${channels_tsv}" "${manifest_json}" "${worker_urls_tsv}" "${worker_env_file}" "${gateway_env_file}"' EXIT

"${uv_bin}" run python "${channels_script}" \
  --modal-environment "${MODAL_ENVIRONMENT}" \
  --environment "${environment}" \
  --output-tsv "${channels_tsv}"

"${gcloud_bin}" auth configure-docker "${artifact_host}" --quiet
if ! "${gcloud_bin}" artifacts repositories describe "${repository}" \
  --location "${region}" \
  --project "${project}" >/dev/null 2>&1; then
  "${gcloud_bin}" artifacts repositories create "${repository}" \
    --location "${region}" \
    --project "${project}" \
    --repository-format docker \
    --description "PolicyEngine household API Cloud Run images" \
    --quiet
fi

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
  printf 'APP__ENVIRONMENT=%s\n' "${environment}" >> "${worker_env_file}"
  printf 'HOUSEHOLD_FAILOVER_CHANNEL=%s\n' "${channel}" >> "${worker_env_file}"
  printf 'HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON=%s\n' \
    "${package_versions_json}" >> "${worker_env_file}"
  append_env_if_set "${worker_env_file}" ANALYTICS__ENABLED
  append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_CONNECTION_NAME
  append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_USERNAME
  append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_PASSWORD
  append_env_if_set "${worker_env_file}" AUTH__ENABLED
  append_env_if_set "${worker_env_file}" AUTH0_ADDRESS_NO_DOMAIN
  append_env_if_set "${worker_env_file}" AUTH0_AUDIENCE_NO_DOMAIN
  append_env_if_set "${worker_env_file}" AI__ENABLED
  append_env_if_set "${worker_env_file}" ANTHROPIC_API_KEY

  deploy_run_service "${gcloud_bin}" run deploy "${worker_service}" \
    --image "${worker_image}" \
    --region "${region}" \
    --project "${project}" \
    --platform managed \
    --no-allow-unauthenticated \
    --min-instances "${worker_min_instances}" \
    --max-instances "${worker_max_instances}" \
    --concurrency "${worker_concurrency}" \
    --timeout 300 \
    --cpu "${worker_cpu}" \
    --memory "${worker_memory}" \
    --service-account "${worker_service_account}" \
    "$(env_args_from_file "${worker_env_file}")" \
    --quiet

  "${gcloud_bin}" run services add-iam-policy-binding "${worker_service}" \
    --region "${region}" \
    --project "${project}" \
    --member "serviceAccount:${gateway_service_account}" \
    --role roles/run.invoker \
    --quiet

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
printf 'APP__ENVIRONMENT=%s\n' "${environment}" >> "${gateway_env_file}"
printf 'MODAL_ENVIRONMENT=%s\n' "${MODAL_ENVIRONMENT}" >> "${gateway_env_file}"
printf 'HOUSEHOLD_FAILOVER_MANIFEST_BUCKET=%s\n' \
  "${manifest_bucket}" >> "${gateway_env_file}"
printf 'HOUSEHOLD_FAILOVER_MANIFEST_BLOB=%s\n' \
  "${manifest_blob}" >> "${gateway_env_file}"
append_env_if_set "${gateway_env_file}" MODAL_TOKEN_ID
append_env_if_set "${gateway_env_file}" MODAL_TOKEN_SECRET
append_env_if_set "${gateway_env_file}" HOUSEHOLD_FAILOVER_FORCE_BACKEND
append_env_if_set "${gateway_env_file}" HOUSEHOLD_FAILOVER_DISABLE_CLOUD_RUN_AUTH

deploy_run_service "${gcloud_bin}" run deploy "${gateway_service}" \
  --image "${gateway_image}" \
  --region "${region}" \
  --project "${project}" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances "${gateway_min_instances}" \
  --max-instances "${gateway_max_instances}" \
  --concurrency "${gateway_concurrency}" \
  --timeout 300 \
  --cpu "${gateway_cpu}" \
  --memory "${gateway_memory}" \
  --service-account "${gateway_service_account}" \
  "$(env_args_from_file "${gateway_env_file}")" \
  --quiet

gateway_url="$(
  "${gcloud_bin}" run services describe "${gateway_service}" \
    --region "${region}" \
    --project "${project}" \
    --format='value(status.url)'
)"

"${curl_bin}" -fsS "${gateway_url}/liveness_check"
github_output "gateway_url" "${gateway_url}"
github_output "manifest_uri" "gs://${manifest_bucket}/${manifest_blob}"

echo "Cloud Run failover gateway deployed: ${gateway_url}"
