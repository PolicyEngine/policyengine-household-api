#!/usr/bin/env bash
set -euo pipefail

cleanup_file="${1:?Usage: modal-cleanup-apps.sh CLEANUP_JSON}"
environment="${MODAL_ENVIRONMENT:-main}"

python -c '
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
for app_name in payload.get("app_names", []):
    print(app_name)
' "${cleanup_file}" | while IFS= read -r app_name; do
  if [[ -z "${app_name}" ]]; then
    continue
  fi
  if ! output="$(uv run modal app stop --yes --env "${environment}" "${app_name}" 2>&1)"; then
    echo "${output}"
    # Stopping a retired app is idempotent: an app that is already stopped or
    # already deleted is the desired end state, so treat both as success and
    # keep going instead of aborting the whole job. Match Modal's specific
    # missing-app message (No App with name '<name>' found in the '<env>'
    # environment.) rather than a generic "not found", which would also swallow
    # unrelated failures like a missing uv/modal CLI or Modal environment.
    if [[ "${output}" == *"already stopped"* \
       || "${output}" == *"No App with name"* ]]; then
      continue
    fi
    exit 1
  fi
  echo "${output}"
done
