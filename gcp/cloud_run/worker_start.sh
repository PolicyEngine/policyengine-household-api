#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8080}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
THREADS="${WEB_THREADS:-5}"

exec gunicorn \
  --bind ":${PORT}" \
  --timeout 300 \
  --workers "${WEB_CONCURRENCY}" \
  --threads "${THREADS}" \
  policyengine_household_api.failover.cloud_run_worker_wsgi:app

