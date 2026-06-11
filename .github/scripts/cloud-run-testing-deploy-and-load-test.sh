#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"

deploy_script="${HOUSEHOLD_CLOUD_RUN_TEST_DEPLOY_SCRIPT:-${script_dir}/cloud-run-deploy-failover.sh}"
load_test_script="${HOUSEHOLD_CLOUD_RUN_LOAD_TEST_SCRIPT:-${script_dir}/cloud_run_gateway_load_test.py}"
gcloud_bin="${GCLOUD_BIN:-gcloud}"
docker_bin="${DOCKER_BIN:-docker}"
uv_bin="${UV_BIN:-uv}"
curl_bin="${CURL_BIN:-curl}"

project="${GOOGLE_CLOUD_PROJECT:-}"
modal_environment="${MODAL_ENVIRONMENT:-staging}"
cloud_run_environment="${HOUSEHOLD_CLOUD_RUN_ENVIRONMENT:-testing}"
region="${HOUSEHOLD_CLOUD_RUN_REGION:-us-central1}"
manifest_bucket="${HOUSEHOLD_FAILOVER_MANIFEST_BUCKET:-}"
test_id="${HOUSEHOLD_CLOUD_RUN_TEST_ID:-${USER:-local}}"
service_prefix="${HOUSEHOLD_CLOUD_RUN_SERVICE_PREFIX:-}"
gateway_service="${HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE:-}"
manifest_blob="${HOUSEHOLD_FAILOVER_MANIFEST_BLOB:-}"
force_backend="${HOUSEHOLD_FAILOVER_FORCE_BACKEND:-cloud_run}"
expected_backend="${HOUSEHOLD_CLOUD_RUN_TEST_EXPECTED_BACKEND:-}"
requests="${HOUSEHOLD_CLOUD_RUN_TEST_REQUESTS:-100}"
concurrency="${HOUSEHOLD_CLOUD_RUN_TEST_CONCURRENCY:-25}"
timeout_seconds="${HOUSEHOLD_CLOUD_RUN_TEST_TIMEOUT_SECONDS:-180}"
max_error_rate="${HOUSEHOLD_CLOUD_RUN_TEST_MAX_ERROR_RATE:-0}"
auth_token="${HOUSEHOLD_API_AUTH_TOKEN:-}"
skip_deploy=0

usage() {
  cat <<'EOF'
Usage: cloud-run-testing-deploy-and-load-test.sh [options]

Deploy an isolated Cloud Run testing namespace, smoke-check it, then run the
Cloud Run gateway load-test harness.

Required:
  --project PROJECT
      or GOOGLE_CLOUD_PROJECT

Optional:
  --manifest-bucket BUCKET
      or HOUSEHOLD_FAILOVER_MANIFEST_BUCKET. Defaults to
      policyengine-household-api-release-manifests for project
      policyengine-household-api.
  --modal-environment ENV
      Modal environment used to resolve current/frontier metadata. Defaults to
      MODAL_ENVIRONMENT or staging.
  --test-id ID
      Namespace suffix for test services and manifest path. Defaults to
      HOUSEHOLD_CLOUD_RUN_TEST_ID, then USER.
  --service-prefix PREFIX
      Defaults to household-api-testing-${test_id}.
  --force-backend cloud_run|modal|none
      Defaults to cloud_run for fallback load testing.
  --requests N
      Defaults to 100.
  --concurrency N
      Defaults to 25.
  --expected-backend modal|cloud_run|none
      Defaults to the forced backend when force-backend is modal or cloud_run.
  --auth-token TOKEN
      Optional bearer token for authenticated deployments.
  --skip-deploy
      Reuse the named testing gateway and run smoke/load tests only.
EOF
}

log() {
  printf '==> %s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

slugify() {
  local value="${1:-local}"
  value="$(printf '%s' "${value}" | tr '[:upper:]_.' '[:lower:]---')"
  value="$(printf '%s' "${value}" | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
  value="$(printf '%s' "${value}" | cut -c1-20)"
  if [ -z "${value}" ]; then
    value="local"
  fi
  printf '%s\n' "${value}"
}

require_command() {
  local command_name="${1:?command is required}"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    die "${command_name} is required on PATH"
  fi
}

require_positive_integer() {
  local name="${1:?name is required}"
  local value="${2:?value is required}"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    die "${name} must be a positive integer"
  fi
}

describe_gateway_url() {
  "${gcloud_bin}" run services describe "${gateway_service}" \
    --region "${region}" \
    --project "${project}" \
    --format='value(status.url)'
}

wait_for_url() {
  local name="${1:?name is required}"
  local url="${2:?url is required}"
  local attempts="${HOUSEHOLD_CLOUD_RUN_TEST_SMOKE_ATTEMPTS:-12}"
  local sleep_seconds="${HOUSEHOLD_CLOUD_RUN_TEST_SMOKE_SLEEP_SECONDS:-5}"
  local attempt

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if "${curl_bin}" -fsS "${url}" >/dev/null; then
      log "${name} passed"
      return
    fi
    sleep "${sleep_seconds}"
  done

  die "${name} did not pass after ${attempts} attempts: ${url}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project)
      shift
      project="${1:-}"
      ;;
    --manifest-bucket)
      shift
      manifest_bucket="${1:-}"
      ;;
    --modal-environment)
      shift
      modal_environment="${1:-}"
      ;;
    --cloud-run-environment)
      shift
      cloud_run_environment="${1:-}"
      ;;
    --region)
      shift
      region="${1:-}"
      ;;
    --test-id)
      shift
      test_id="${1:-}"
      ;;
    --service-prefix)
      shift
      service_prefix="${1:-}"
      ;;
    --gateway-service)
      shift
      gateway_service="${1:-}"
      ;;
    --manifest-blob)
      shift
      manifest_blob="${1:-}"
      ;;
    --force-backend)
      shift
      force_backend="${1:-}"
      ;;
    --expected-backend)
      shift
      expected_backend="${1:-}"
      ;;
    --requests)
      shift
      requests="${1:-}"
      ;;
    --concurrency)
      shift
      concurrency="${1:-}"
      ;;
    --timeout-seconds)
      shift
      timeout_seconds="${1:-}"
      ;;
    --max-error-rate)
      shift
      max_error_rate="${1:-}"
      ;;
    --auth-token)
      shift
      auth_token="${1:-}"
      ;;
    --skip-deploy)
      skip_deploy=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
  shift || true
done

if [ -z "${project}" ]; then
  die "--project or GOOGLE_CLOUD_PROJECT is required"
fi

if [ -z "${manifest_bucket}" ] && [ "${project}" = "policyengine-household-api" ]; then
  manifest_bucket="policyengine-household-api-release-manifests"
fi
if [ -z "${manifest_bucket}" ]; then
  die "--manifest-bucket or HOUSEHOLD_FAILOVER_MANIFEST_BUCKET is required"
fi

test_id="$(slugify "${test_id}")"
if [ -z "${service_prefix}" ]; then
  service_prefix="household-api-testing-${test_id}"
fi
if [ -z "${gateway_service}" ]; then
  gateway_service="${service_prefix}-gateway"
fi
if [ -z "${manifest_blob}" ]; then
  manifest_blob="testing/${test_id}/failover-manifest.json"
fi

case "${force_backend}" in
  cloud_run|modal|none) ;;
  *) die "--force-backend must be cloud_run, modal, or none" ;;
esac

if [ -z "${expected_backend}" ]; then
  case "${force_backend}" in
    cloud_run|modal) expected_backend="${force_backend}" ;;
    none) expected_backend="none" ;;
  esac
fi
case "${expected_backend}" in
  cloud_run|modal|none) ;;
  *) die "--expected-backend must be cloud_run, modal, or none" ;;
esac

require_positive_integer "--requests" "${requests}"
require_positive_integer "--concurrency" "${concurrency}"
require_command "${gcloud_bin}"
require_command "${curl_bin}"
require_command "${uv_bin}"
if [ "${skip_deploy}" -eq 0 ]; then
  require_command "${docker_bin}"
fi

export GOOGLE_CLOUD_PROJECT="${project}"
export MODAL_ENVIRONMENT="${modal_environment}"
export HOUSEHOLD_CLOUD_RUN_ENVIRONMENT="${cloud_run_environment}"
export HOUSEHOLD_CLOUD_RUN_REGION="${region}"
export HOUSEHOLD_CLOUD_RUN_SERVICE_PREFIX="${service_prefix}"
export HOUSEHOLD_CLOUD_RUN_GATEWAY_SERVICE="${gateway_service}"
export HOUSEHOLD_FAILOVER_MANIFEST_BUCKET="${manifest_bucket}"
export HOUSEHOLD_FAILOVER_MANIFEST_BLOB="${manifest_blob}"
export GCLOUD_BIN="${gcloud_bin}"
export DOCKER_BIN="${docker_bin}"
export UV_BIN="${uv_bin}"
export CURL_BIN="${curl_bin}"

if [ -z "${GITHUB_SHA:-}" ]; then
  GITHUB_SHA="$(git -C "${repo_root}" rev-parse --short HEAD)"
  export GITHUB_SHA
fi

if [ "${force_backend}" = "none" ]; then
  unset HOUSEHOLD_FAILOVER_FORCE_BACKEND
else
  export HOUSEHOLD_FAILOVER_FORCE_BACKEND="${force_backend}"
fi

log "Testing namespace: ${service_prefix}"
log "Cloud Run environment: ${cloud_run_environment}"
log "Modal environment: ${modal_environment}"
log "Manifest: gs://${manifest_bucket}/${manifest_blob}"
log "Gateway service: ${gateway_service}"
log "This script does not grant IAM; required runtime roles must already exist."

deploy_output="$(mktemp)"
trap 'rm -f "${deploy_output}"' EXIT

if [ "${skip_deploy}" -eq 0 ]; then
  log "Deploying isolated Cloud Run testing services"
  GITHUB_OUTPUT="${deploy_output}" bash "${deploy_script}"
else
  log "Skipping deployment and reusing existing gateway service"
fi

gateway_url="$(
  awk -F= '$1 == "gateway_url" {print substr($0, index($0, "=") + 1)}' \
    "${deploy_output}" | tail -n 1
)"
if [ -z "${gateway_url}" ]; then
  gateway_url="$(describe_gateway_url)"
fi
if [ -z "${gateway_url}" ]; then
  die "could not resolve Cloud Run gateway URL"
fi

log "Gateway URL: ${gateway_url}"
wait_for_url "liveness_check" "${gateway_url}/liveness_check"
wait_for_url "readiness_check" "${gateway_url}/readiness_check"

load_test_args=(
  run
  python
  "${load_test_script}"
  --base-url
  "${gateway_url}"
  --requests
  "${requests}"
  --concurrency
  "${concurrency}"
  --timeout-seconds
  "${timeout_seconds}"
  --max-error-rate
  "${max_error_rate}"
)

if [ "${expected_backend}" != "none" ]; then
  load_test_args+=(--expected-backend "${expected_backend}")
fi
if [ -n "${auth_token}" ]; then
  load_test_args+=(--auth-token "${auth_token}")
fi

log "Running load test: requests=${requests}, concurrency=${concurrency}"
"${uv_bin}" "${load_test_args[@]}"

log "Testing deployment passed"
printf 'gateway_url=%s\n' "${gateway_url}"
