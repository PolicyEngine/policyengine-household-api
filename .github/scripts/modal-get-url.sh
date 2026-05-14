#!/usr/bin/env bash
set -euo pipefail

environment="${MODAL_ENVIRONMENT:-main}"
app_name="${HOUSEHOLD_MODAL_GATEWAY_APP_NAME:-policyengine-household-api-gateway}"
function_name="${HOUSEHOLD_MODAL_GATEWAY_FUNCTION_NAME:-web_app}"

uv run python - "${app_name}" "${function_name}" "${environment}" <<'PY'
from __future__ import annotations

import sys

import modal


app_name, function_name, environment = sys.argv[1:4]
function = modal.Function.from_name(
    app_name,
    function_name,
    environment_name=environment,
)
url = function.get_web_url()
if not url:
    raise SystemExit(
        f"Modal function `{app_name}.{function_name}` has no web URL"
    )
print(url)
PY
