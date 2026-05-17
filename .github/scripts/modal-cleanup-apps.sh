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
  if ! output="$(uv run modal app stop --env "${environment}" "${app_name}" 2>&1)"; then
    echo "${output}"
    if [[ "${output}" == *"already stopped"* ]]; then
      continue
    fi
    exit 1
  fi
  echo "${output}"
done
