#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8080}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-2}"
THREADS="${WEB_THREADS:-16}"

exec gunicorn \
  --bind ":${PORT}" \
  --timeout 300 \
  --workers "${WEB_CONCURRENCY}" \
  --worker-class gthread \
  --threads "${THREADS}" \
  policyengine_household_api.failover.cloud_run_gateway_wsgi:app
