#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8080}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
THREADS="${WEB_THREADS:-25}"
WEB_TIMEOUT="${WEB_TIMEOUT:-1200}"

exec gunicorn \
  --bind ":${PORT}" \
  --timeout "${WEB_TIMEOUT}" \
  --workers "${WEB_CONCURRENCY}" \
  --threads "${THREADS}" \
  policyengine_household_api.failover.cloud_run_worker_wsgi:app
