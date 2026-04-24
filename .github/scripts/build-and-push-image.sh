#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARTIFACT_TAG="${IMAGE_NAME:?}:${GITHUB_SHA:?}"
GHCR_SHA_TAG="ghcr.io/${GITHUB_REPOSITORY:?}:${GITHUB_SHA}"
GHCR_LATEST_TAG="ghcr.io/${GITHUB_REPOSITORY:?}:latest"

docker build \
  -f ./gcp/policyengine_household_api/Dockerfile.production \
  -t "${ARTIFACT_TAG}" \
  .
docker push "${ARTIFACT_TAG}"

if [ "${GITHUB_EVENT_NAME:-}" = "push" ] && [ "${GITHUB_REF:-}" = "refs/heads/main" ]; then
  docker tag "${ARTIFACT_TAG}" "${GHCR_SHA_TAG}"
  docker push "${GHCR_SHA_TAG}"
  docker tag "${ARTIFACT_TAG}" "${GHCR_LATEST_TAG}"
  docker push "${GHCR_LATEST_TAG}"
fi
