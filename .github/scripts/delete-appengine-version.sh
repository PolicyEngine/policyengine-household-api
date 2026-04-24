#!/bin/bash

set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:?SERVICE_NAME must be set}"
VERSION="${VERSION:?VERSION must be set}"

echo "Deleting App Engine version ${VERSION} from service ${SERVICE_NAME}"
gcloud app versions delete "${VERSION}" --service="${SERVICE_NAME}" --quiet
