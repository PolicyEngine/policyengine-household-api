#!/bin/bash

# Verify App Engine deployment
set -e

# Get required environment variables
SERVICE_NAME="${SERVICE_NAME}"

if [ -z "$SERVICE_NAME" ]; then
    echo "Error: SERVICE_NAME environment variable must be set"
    exit 1
fi

echo "Verifying App Engine deployment..."
echo "Service: $SERVICE_NAME"

# List recent versions to verify deployment
gcloud app versions list \
    --service="$SERVICE_NAME" \
    --limit=5

echo "Deployment verification completed"
