#!/usr/bin/env bash
# Warm the Modal worker behind the Cloud Run gateway before the gateway's
# Modal-primary integration tests.
#
# The Modal workers scale to zero shortly after a deploy, and the first boot
# per runner profile CREATES the memory snapshot rather than restoring one:
# it runs the full snap=True hook (country-system builds plus the parameter
# at-instant prewarm, issue #1624), which takes minutes on Modal CPU -- far
# past the gateway's 90s Modal request timeout. This sends a real
# authenticated calculate through the gateway for the channel under test and
# retries until it returns 200, so the test step starts only once a
# snapshot-backed worker is actually serving on the same path it asserts on.
#
# The payload can stay cheap: snapshot-restored containers already hold the
# prewarmed parameter caches, so any 200 through the gateway proves readiness
# for the heavy test households too.
#
# Best-effort: this never exits non-zero. A worker that cannot be warmed only
# emits a warning; the deployed test step remains the gate.
set -uo pipefail

channel="${1:?Usage: cloud-run-warm-modal-via-gateway.sh CHANNEL}"
curl_bin="${CURL_BIN:-curl}"

base_url="${HOUSEHOLD_API_BASE_URL:-}"
auth_token="${HOUSEHOLD_API_AUTH_TOKEN:-}"
# 600s: snapshot creation now includes the parameter prewarm (~1-2 min on
# Modal CPU) on top of the country-system builds, so 300s could expire while
# the first post-deploy boot is still snapshotting (issue #1624).
total_timeout="${HOUSEHOLD_GATEWAY_WARM_TIMEOUT_SECONDS:-600}"
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
