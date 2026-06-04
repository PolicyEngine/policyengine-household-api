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

append_env_if_set() {
  local env_file="${1:?env file is required}"
  local key="${2:?env key is required}"
  if [ -n "${!key:-}" ]; then
    append_env_value "${env_file}" "${key}" "${!key}"
  fi
}

append_env_value() {
  local env_file="${1:?env file is required}"
  local key="${2:?env key is required}"
  local value="${3:-}"
  local line

  printf '%s: |-\n' "${key}" >> "${env_file}"
  while IFS= read -r line || [ -n "${line}" ]; do
    printf '  %s\n' "${line}" >> "${env_file}"
  done <<EOF
${value}
EOF
}

env_args_from_file() {
  local env_file="${1:?env file is required}"
  if [ ! -s "${env_file}" ]; then
    return
  fi
  printf '%s\n' "--env-vars-file=${env_file}"
}

sync_secret_if_set() {
  local secrets_file="${1:?secrets file is required}"
  local key="${2:?secret env key is required}"
  local secret_override_key="HOUSEHOLD_CLOUD_RUN_SECRET_${key}"
  local secret_override_value="${!secret_override_key:-}"
  local secret_name="${secret_override_value:-${secret_prefix}-${key}}"
  local secret_value_file

  if [ -z "${!key:-}" ]; then
    return
  fi

  if ! "${gcloud_bin}" secrets describe "${secret_name}" \
    --project "${project}" >/dev/null 2>&1; then
    "${gcloud_bin}" secrets create "${secret_name}" \
      --project "${project}" \
      --replication-policy automatic \
      --quiet
  fi

  secret_value_file="$(mktemp)"
  chmod 600 "${secret_value_file}"
  printf '%s' "${!key}" > "${secret_value_file}"
  if ! "${gcloud_bin}" secrets versions add "${secret_name}" \
    --project "${project}" \
    --data-file "${secret_value_file}" >/dev/null; then
    rm -f "${secret_value_file}"
    return 1
  fi
  rm -f "${secret_value_file}"

  printf '%s=%s:latest\n' "${key}" "${secret_name}" >> "${secrets_file}"
}

secret_args_from_file() {
  local secrets_file="${1:?secrets file is required}"
  local joined=""
  local line

  if [ ! -s "${secrets_file}" ]; then
    return
  fi

  while IFS= read -r line; do
    if [ -z "${joined}" ]; then
      joined="${line}"
    else
      joined="${joined},${line}"
    fi
  done < "${secrets_file}"
  printf '%s\n' "--set-secrets=${joined}"
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
secret_prefix="${HOUSEHOLD_CLOUD_RUN_SECRET_PREFIX:-${service_prefix}}"
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
gateway_concurrency="${HOUSEHOLD_CLOUD_RUN_GATEWAY_CONCURRENCY:-32}"
gateway_cpu="${HOUSEHOLD_CLOUD_RUN_GATEWAY_CPU:-1}"
gateway_memory="${HOUSEHOLD_CLOUD_RUN_GATEWAY_MEMORY:-512Mi}"

worker_min_instances="${HOUSEHOLD_CLOUD_RUN_WORKER_MIN_INSTANCES:-0}"
worker_max_instances="${HOUSEHOLD_CLOUD_RUN_WORKER_MAX_INSTANCES:-100}"
worker_concurrency="${HOUSEHOLD_CLOUD_RUN_WORKER_CONCURRENCY:-25}"
worker_cpu="${HOUSEHOLD_CLOUD_RUN_WORKER_CPU:-1}"
worker_memory="${HOUSEHOLD_CLOUD_RUN_WORKER_MEMORY:-4Gi}"

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
  : > "${worker_secrets_file}"
  append_env_value "${worker_env_file}" APP__ENVIRONMENT "${environment}"
  append_env_value "${worker_env_file}" HOUSEHOLD_FAILOVER_CHANNEL "${channel}"
  append_env_value \
    "${worker_env_file}" \
    HOUSEHOLD_FAILOVER_PACKAGE_VERSIONS_JSON \
    "${package_versions_json}"
  append_env_if_set "${worker_env_file}" ANALYTICS__ENABLED
  append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_CONNECTION_NAME
  append_env_if_set "${worker_env_file}" USER_ANALYTICS_DB_USERNAME
  append_env_if_set "${worker_env_file}" AUTH__ENABLED
  append_env_if_set "${worker_env_file}" AUTH0_ADDRESS_NO_DOMAIN
  append_env_if_set "${worker_env_file}" AUTH0_AUDIENCE_NO_DOMAIN
  append_env_if_set "${worker_env_file}" AI__ENABLED
  sync_secret_if_set \
    "${worker_secrets_file}" \
    USER_ANALYTICS_DB_PASSWORD
  sync_secret_if_set \
    "${worker_secrets_file}" \
    ANTHROPIC_API_KEY

  worker_env_args=()
  worker_secret_args=()
  if worker_env_arg="$(env_args_from_file "${worker_env_file}")"; then
    if [ -n "${worker_env_arg}" ]; then
      worker_env_args+=("${worker_env_arg}")
    fi
  fi
  if worker_secret_arg="$(secret_args_from_file "${worker_secrets_file}")"; then
    if [ -n "${worker_secret_arg}" ]; then
      worker_secret_args+=("${worker_secret_arg}")
    fi
  fi

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
    "${worker_env_args[@]}" \
    "${worker_secret_args[@]}" \
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
: > "${gateway_secrets_file}"
append_env_value "${gateway_env_file}" APP__ENVIRONMENT "${environment}"
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
sync_secret_if_set \
  "${gateway_secrets_file}" \
  MODAL_TOKEN_ID
sync_secret_if_set \
  "${gateway_secrets_file}" \
  MODAL_TOKEN_SECRET

gateway_env_args=()
gateway_secret_args=()
if gateway_env_arg="$(env_args_from_file "${gateway_env_file}")"; then
  if [ -n "${gateway_env_arg}" ]; then
    gateway_env_args+=("${gateway_env_arg}")
  fi
fi
if gateway_secret_arg="$(secret_args_from_file "${gateway_secrets_file}")"; then
  if [ -n "${gateway_secret_arg}" ]; then
    gateway_secret_args+=("${gateway_secret_arg}")
  fi
fi

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
  "${gateway_env_args[@]}" \
  "${gateway_secret_args[@]}" \
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
