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

request_version="$(
  BASE_URL="${base_url}" \
  CHANNEL="${channel}" \
  ROUTE_MODE="${route_mode}" \
  python -c '
import json
import os
import sys
import time
from urllib import error, request

base_url = os.environ["BASE_URL"].rstrip("/")
channel = os.environ["CHANNEL"]
route_mode = os.environ["ROUTE_MODE"]

# The gateway is often freshly deployed (cold) when this runs, and all four
# matrix jobs hit it at once; retry so a slow first response does not fail
# the lane before any test executes.
versions = None
last_error = None
for attempt in range(5):
    if attempt:
        time.sleep(15)
    try:
        with request.urlopen(
            f"{base_url}/versions/us", timeout=60
        ) as response:
            versions = json.loads(response.read().decode("utf-8"))
        break
    except error.HTTPError as exc:
        last_error = f"HTTP {exc.code}"
    except (error.URLError, TimeoutError, OSError) as exc:
        last_error = repr(exc)
if versions is None:
    sys.exit(f"Could not load active Modal channels: {last_error}")

package_version = versions.get(channel)
if not package_version:
    sys.exit(f"Modal staging does not expose `{channel}` for US")

if route_mode == "channel":
    print(channel)
else:
    print(package_version)
'
)"

echo "Running deployed tests against Modal ${channel} via ${route_mode} routing"
HOUSEHOLD_API_REQUEST_VERSION="${request_version}" \
HOUSEHOLD_API_EXPECTED_CHANNEL="${channel}" \
HOUSEHOLD_API_ROUTE_MODE="${route_mode}" \
  bash "${deployed_tests_script}"
