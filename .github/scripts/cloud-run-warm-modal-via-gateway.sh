#!/usr/bin/env bash
# Warm the Modal worker behind the Cloud Run gateway before the gateway's
# Modal-primary integration tests.
#
# The Modal workers scale to zero shortly after a deploy, so the first
# /us/calculate routed through the gateway pays a cold start (container boot +
# country model load) that can exceed the gateway's Modal request timeout and
# return 503. This sends a real authenticated calculate through the gateway for
# the channel under test and waits until it returns 200, so the test step then
# exercises a warm worker over the same path it asserts on.
#
# It must be a full authenticated calculate (not a liveness ping): the cold cost
# is loading the country model on the first real calculation, so a cheap request
# would warm the container but not the calculation path the tests exercise.
#
# Best-effort: this never exits non-zero. A worker that cannot be warmed only
# emits a warning; the deployed test step remains the gate.
set -uo pipefail

channel="${1:?Usage: cloud-run-warm-modal-via-gateway.sh CHANNEL}"
curl_bin="${CURL_BIN:-curl}"

base_url="${HOUSEHOLD_API_BASE_URL:-}"
auth_token="${HOUSEHOLD_API_AUTH_TOKEN:-}"
total_timeout="${HOUSEHOLD_GATEWAY_WARM_TIMEOUT_SECONDS:-300}"
attempt_timeout="${HOUSEHOLD_GATEWAY_WARM_ATTEMPT_TIMEOUT_SECONDS:-120}"

if [ -z "${base_url}" ] || [ -z "${auth_token}" ]; then
  echo "::warning::HOUSEHOLD_API_BASE_URL and HOUSEHOLD_API_AUTH_TOKEN are required to warm the gateway; skipping."
  exit 0
fi

url="${base_url%/}/us/calculate"

# Minimal but valid US calculation. The "version" field is read by the gateway
# to route to the channel under test (channel-name routing), then stripped
# before the request reaches the worker.
body="$(
  cat <<JSON
{"version":"${channel}","household":{"people":{"parent":{"age":{"2026":35},"employment_income":{"2026":60000}},"child":{"age":{"2026":6}}},"tax_units":{"tax_unit":{"members":["parent","child"],"ctc":{"2026":null}}},"spm_units":{"spm_unit":{"members":["parent","child"]}},"households":{"household":{"members":["parent","child"],"state_name":{"2026":"AZ"}}}}}
JSON
)"

echo "Warming Modal ${channel} worker through ${url} (up to ${total_timeout}s)..."
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
      echo "Modal ${channel} worker is warm (HTTP ${code})."
      exit 0
      ;;
  esac
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    echo "::warning::Modal ${channel} worker did not return 2xx within ${total_timeout}s (last HTTP ${code:-none}); continuing to tests anyway."
    exit 0
  fi
  echo "Modal ${channel} not warm yet (HTTP ${code:-timeout}); retrying..."
  sleep 5
done
