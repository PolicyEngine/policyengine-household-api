#!/bin/bash

# Set traffic to new App Engine version
set -e

# Get required environment variables
SERVICE_NAME="${SERVICE_NAME}"
VERSION="${VERSION}"

if [ -z "$SERVICE_NAME" ] || [ -z "$VERSION" ]; then
    echo "Error: SERVICE_NAME and VERSION environment variables must be set"
    exit 1
fi

echo "Setting traffic to new App Engine version..."
echo "Service: $SERVICE_NAME"
echo "Version: $VERSION"

# Set traffic to the new version
gcloud app services set-traffic "$SERVICE_NAME" \
    --splits="$VERSION=1.0"

echo "Traffic successfully set to version $VERSION"
