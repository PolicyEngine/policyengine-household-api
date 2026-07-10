# Shared helpers for Cloud Run deploy scripts. Source this file; do not run it.
#
# Callers must set (or accept the defaults for) the globals these functions
# read: project, region, repository, environment, service_prefix,
# secret_prefix, and the *_bin binaries below.

curl_bin="${CURL_BIN:-curl}"
docker_bin="${DOCKER_BIN:-docker}"
gcloud_bin="${GCLOUD_BIN:-gcloud}"
uv_bin="${UV_BIN:-uv}"
output_file="${GITHUB_OUTPUT:-}"

startup_probe_script="${CLOUD_RUN_STARTUP_PROBE_SCRIPT:-.github/scripts/cloud_run_apply_startup_probe.py}"

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

is_truthy() {
  case "${1:-}" in
    1 | true | True | TRUE | yes | Yes | YES)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

require_analytics_cloud_tasks_env() {
  if ! is_truthy "${ANALYTICS__ENABLED:-false}"; then
    return
  fi

  require_env \
    ANALYTICS__CLOUD_TASKS__PROJECT \
    ANALYTICS__CLOUD_TASKS__LOCATION \
    ANALYTICS__CLOUD_TASKS__QUEUE \
    ANALYTICS__CLOUD_TASKS__SERVICE_ACCOUNT_EMAIL
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

append_observability_env() {
  local env_file="${1:?env file is required}"
  local observability_project="${OBSERVABILITY_GOOGLE_CLOUD_PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"

  append_env_value "${env_file}" OBSERVABILITY_ENVIRONMENT "${environment}"
  append_env_value "${env_file}" OBSERVABILITY_PLATFORM "google_cloud_run"
  append_env_value "${env_file}" OBSERVABILITY_GOOGLE_CLOUD_PROJECT "${observability_project}"
  append_env_if_set "${env_file}" OBSERVABILITY_ENABLED
  append_env_if_set "${env_file}" OBSERVABILITY_LOG_DESTINATIONS
  append_env_if_set "${env_file}" OBSERVABILITY_LOG_PROFILE
  append_env_if_set "${env_file}" OBSERVABILITY_LOG_QUEUE_MAXSIZE
  append_env_if_set "${env_file}" OBSERVABILITY_LOG_QUEUE_CLOSE_TIMEOUT_SECONDS
  append_env_if_set "${env_file}" OBSERVABILITY_GOOGLE_CLOUD_LOG_NAME
  append_env_if_set "${env_file}" OBSERVABILITY_GOOGLE_WRITE_TIMEOUT_SECONDS
  append_env_if_set "${env_file}" OBSERVABILITY_REQUEST_LOGS_ENABLED
  append_env_if_set "${env_file}" OBSERVABILITY_LOG_RAW_IP
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

configure_artifact_registry() {
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
}

apply_startup_probe() {
  # Ensure the service only reports ready once it actually serves HTTP.
  # `gcloud run deploy` alone passes on a TCP port check, which gunicorn's
  # master satisfies before workers finish booting — a crash-looping app can
  # deploy "successfully" without this. `services replace` waits for the new
  # revision to become ready, so a failing probe fails this deploy script.
  local service="${1:?service is required}"
  local period_seconds="${2:?period seconds is required}"
  local timeout_seconds="${3:?timeout seconds is required}"
  local failure_threshold="${4:?failure threshold is required}"
  local service_yaml

  service_yaml="$(mktemp)"
  "${gcloud_bin}" run services describe "${service}" \
    --region "${region}" \
    --project "${project}" \
    --format export > "${service_yaml}"
  "${uv_bin}" run python "${startup_probe_script}" \
    --input-yaml "${service_yaml}" \
    --output-yaml "${service_yaml}" \
    --path /liveness_check \
    --period-seconds "${period_seconds}" \
    --timeout-seconds "${timeout_seconds}" \
    --failure-threshold "${failure_threshold}"
  "${gcloud_bin}" run services replace "${service_yaml}" \
    --region "${region}" \
    --project "${project}" \
    --quiet
  rm -f "${service_yaml}"
}
