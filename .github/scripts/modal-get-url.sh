#!/usr/bin/env bash
set -euo pipefail

workspace="${MODAL_WORKSPACE:-policyengine}"
environment="${MODAL_ENVIRONMENT:-main}"
app_name="${HOUSEHOLD_MODAL_GATEWAY_APP_NAME:-policyengine-household-api-gateway}"

if [[ "${environment}" == "main" ]]; then
  echo "https://${workspace}--${app_name}-web-app.modal.run"
else
  echo "https://${workspace}-${environment}--${app_name}-web-app.modal.run"
fi

