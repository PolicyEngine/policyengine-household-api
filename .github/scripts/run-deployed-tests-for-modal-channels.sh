#!/usr/bin/env bash
set -euo pipefail

base_url="${HOUSEHOLD_API_BASE_URL:?HOUSEHOLD_API_BASE_URL must be set}"

channels="$(
  BASE_URL="${base_url}" python -c '
import json
import os
import sys
from urllib import error, request

base_url = os.environ["BASE_URL"].rstrip("/")
try:
    with request.urlopen(f"{base_url}/versions/us", timeout=30) as response:
        versions = json.loads(response.read().decode("utf-8"))
except error.HTTPError as exc:
    sys.exit(f"Could not load active Modal channels: HTTP {exc.code}")

active = [channel for channel in ("current", "frontier") if versions.get(channel)]
if "current" not in active:
    sys.exit("Modal staging must expose a current channel before tests run")
print("\n".join(active))
'
)"

while IFS= read -r channel; do
  if [ -z "${channel}" ]; then
    continue
  fi
  echo "Running deployed tests against Modal ${channel}"
  HOUSEHOLD_API_REQUEST_VERSION="${channel}" \
    bash .github/scripts/run-deployed-tests.sh
done <<< "${channels}"
