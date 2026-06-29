#!/usr/bin/env bash
# Warm the Cloud Run fallback path before the forced-fallback test.
#
# The workers run at min-instances=0, so the first request triggers a cold
# start (image pull + container boot + full app import) that can take minutes
# and exceed the deployed-test read timeout. This first pings each worker's
# liveness endpoint and then runs a real authenticated calculate through the
# public gateway so the test step exercises the same fallback dispatch and
# calculation path it asserts on.
#
# The workers are private (--no-allow-unauthenticated), so an unauthenticated
# request is rejected at the front door without starting a container; we send
# an IAM identity token so the request actually reaches the worker and triggers
# the cold start.
#
# Best-effort: this never exits non-zero. A path that cannot be warmed only
# emits a warning; the deployed test step remains the gate.
set -uo pipefail

gcloud_bin="${GCLOUD_BIN:-gcloud}"
curl_bin="${CURL_BIN:-curl}"

project="${GOOGLE_CLOUD_PROJECT:-}"
region="${HOUSEHOLD_CLOUD_RUN_REGION:-us-central1}"
gateway_service="${CLOUD_RUN_GATEWAY_SERVICE:-}"
base_url="${HOUSEHOLD_API_BASE_URL:-}"
auth_token="${HOUSEHOLD_API_AUTH_TOKEN:-}"
channels="${HOUSEHOLD_CLOUD_RUN_WARM_CHANNELS:-current frontier}"
total_timeout="${HOUSEHOLD_CLOUD_RUN_WARM_TIMEOUT_SECONDS:-300}"
attempt_timeout="${HOUSEHOLD_CLOUD_RUN_WARM_ATTEMPT_TIMEOUT_SECONDS:-120}"

if [ -z "${project}" ] || [ -z "${gateway_service}" ]; then
  echo "::warning::GOOGLE_CLOUD_PROJECT and CLOUD_RUN_GATEWAY_SERVICE are required to warm workers; skipping."
  exit 0
fi

worker_prefix="${gateway_service%-gateway}"

warm_worker() {
  local service="$1"
  local url token code deadline
  url="$(
    "${gcloud_bin}" run services describe "${service}" \
      --region "${region}" \
      --project "${project}" \
      --format='value(status.url)' 2>/dev/null || true
  )"
  if [ -z "${url}" ]; then
    echo "::warning::Could not resolve URL for ${service}; skipping warm-up."
    return 0
  fi

  token="$(
    "${gcloud_bin}" auth print-identity-token --audiences="${url}" \
      2>/dev/null || true
  )"
  if [ -z "${token}" ]; then
    echo "::warning::Could not mint identity token for ${service}; skipping warm-up."
    return 0
  fi

  echo "Warming ${service} via ${url}/liveness_check (up to ${total_timeout}s)..."
  deadline=$(( $(date +%s) + total_timeout ))
  while :; do
    code="$(
      "${curl_bin}" -sS -o /dev/null -w '%{http_code}' \
        --max-time "${attempt_timeout}" \
        -H "Authorization: Bearer ${token}" \
        "${url}/liveness_check" || true
    )"
    case "${code}" in
      2*)
        echo "${service} is warm (HTTP ${code})."
        return 0
        ;;
      401 | 403)
        echo "::warning::${service} rejected the warm-up request (HTTP ${code}); the worker was not warmed."
        return 0
        ;;
    esac
    if [ "$(date +%s)" -ge "${deadline}" ]; then
      echo "::warning::${service} did not respond within ${total_timeout}s; continuing to tests anyway."
      return 0
    fi
    sleep 5
  done
}

warm_gateway_calculate() {
  local channel="$1"
  local url code deadline body

  if [ -z "${base_url}" ] || [ -z "${auth_token}" ]; then
    echo "::warning::HOUSEHOLD_API_BASE_URL and HOUSEHOLD_API_AUTH_TOKEN are required to warm the gateway calculate path; skipping ${channel}."
    return 0
  fi

  url="${base_url%/}/us/calculate"
  body="$(
    cat <<JSON
{"version":"${channel}","household":{"people":{"parent":{"age":{"2026":35},"employment_income":{"2026":60000}},"child":{"age":{"2026":6}}},"tax_units":{"tax_unit":{"members":["parent","child"],"ctc":{"2026":null}}},"spm_units":{"spm_unit":{"members":["parent","child"]}},"households":{"household":{"members":["parent","child"],"state_name":{"2026":"AZ"}}}}}
JSON
  )"

  echo "Warming Cloud Run ${channel} fallback through ${url} (up to ${total_timeout}s)..."
  deadline=$(( $(date +%s) + total_timeout ))
  while :; do
    code="$(
      "${curl_bin}" -sS -o /dev/null -w '%{http_code}' \
        --max-time "${attempt_timeout}" \
        -X POST \
        -H "Authorization: Bearer ${auth_token}" \
        -H "Content-Type: application/json" \
        -d "${body}" \
        "${url}" || true
    )"
    case "${code}" in
      2*)
        echo "Cloud Run ${channel} fallback calculate path is warm (HTTP ${code})."
        return 0
        ;;
      401 | 403)
        echo "::warning::Gateway rejected the ${channel} calculate warm-up request (HTTP ${code}); the calculate path was not warmed."
        return 0
        ;;
    esac
    if [ "$(date +%s)" -ge "${deadline}" ]; then
      echo "::warning::Cloud Run ${channel} fallback calculate path did not return 2xx within ${total_timeout}s (last HTTP ${code:-none}); continuing to tests anyway."
      return 0
    fi
    echo "Cloud Run ${channel} fallback calculate path not warm yet (HTTP ${code:-timeout}); retrying..."
    sleep 5
  done
}

read -ra warm_channels <<< "${channels}"
pids=()
for channel in "${warm_channels[@]}"; do
  warm_worker "${worker_prefix}-${channel}-worker" &
  pids+=("$!")
done
wait "${pids[@]}"

for channel in "${warm_channels[@]}"; do
  warm_gateway_calculate "${channel}"
done
exit 0
