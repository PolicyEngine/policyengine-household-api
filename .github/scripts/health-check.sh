#!/bin/bash

set -euo pipefail

BASE_URL="${1:?Base URL required}"
MAX_ATTEMPTS="${2:-10}"
SLEEP_SECONDS="${3:-15}"

LIVENESS_URL="${BASE_URL%/}/liveness_check"
READINESS_URL="${BASE_URL%/}/readiness_check"

echo "Checking liveness at: $LIVENESS_URL"
echo "Checking readiness at: $READINESS_URL"

for i in $(seq 1 "$MAX_ATTEMPTS"); do
  if curl --fail --silent "$LIVENESS_URL" >/dev/null 2>&1 && \
     curl --fail --silent "$READINESS_URL" >/dev/null 2>&1; then
    echo "Health checks passed"
    exit 0
  fi

  echo "Attempt $i/$MAX_ATTEMPTS failed; waiting ${SLEEP_SECONDS}s"
  sleep "$SLEEP_SECONDS"
done

echo "Health checks failed after $MAX_ATTEMPTS attempts"
exit 1
