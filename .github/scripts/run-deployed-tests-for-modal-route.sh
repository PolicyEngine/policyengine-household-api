#!/usr/bin/env bash
set -euo pipefail

channel="${1:?Usage: run-deployed-tests-for-modal-route.sh CHANNEL ROUTE_MODE}"
route_mode="${2:?Usage: run-deployed-tests-for-modal-route.sh CHANNEL ROUTE_MODE}"
base_url="${HOUSEHOLD_API_BASE_URL:-}"
modal_get_url_script="${HOUSEHOLD_MODAL_GET_URL_SCRIPT:-.github/scripts/modal-get-url.sh}"
deployed_tests_script="${HOUSEHOLD_DEPLOYED_TESTS_SCRIPT:-.github/scripts/run-deployed-tests.sh}"

if [ -z "${base_url}" ]; then
  base_url="$(bash "${modal_get_url_script}")"
fi
if [ -z "${base_url}" ]; then
  echo "HOUSEHOLD_API_BASE_URL must be set or resolvable from Modal" >&2
  exit 1
fi
export HOUSEHOLD_API_BASE_URL="${base_url}"

if [ "${channel}" != "current" ] && [ "${channel}" != "frontier" ]; then
  echo "CHANNEL must be current or frontier, got ${channel}" >&2
  exit 1
fi

if [ "${route_mode}" != "channel" ] && [ "${route_mode}" != "exact" ]; then
  echo "ROUTE_MODE must be channel or exact, got ${route_mode}" >&2
  exit 1
fi

# The request version (channel name or the exact live model version) is
# resolved inside the test session by the `request_version` fixture in
# tests/deployed/conftest.py, so resolution failures appear in the pytest
# report instead of killing the step before any test output.
echo "Running deployed tests against Modal ${channel} via ${route_mode} routing"
HOUSEHOLD_API_EXPECTED_CHANNEL="${channel}" \
HOUSEHOLD_API_ROUTE_MODE="${route_mode}" \
  bash "${deployed_tests_script}"
