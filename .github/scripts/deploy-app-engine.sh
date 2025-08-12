#!/bin/bash

# Deploy to Google Cloud App Engine using pre-built Docker image
set -e

# Get required environment variables
IMAGE_NAME="${IMAGE_NAME}"
IMAGE_TAG="${IMAGE_TAG}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT}"
APP_YAML_PATH="${APP_YAML_PATH}"

if [ -z "$IMAGE_NAME" ] || [ -z "$IMAGE_TAG" ] || [ -z "$SERVICE_ACCOUNT" ] || [ -z "$APP_YAML_PATH" ]; then
    echo "Error: Required environment variables not set"
    echo "IMAGE_NAME: $IMAGE_NAME"
    echo "IMAGE_TAG: $IMAGE_TAG"
    echo "SERVICE_ACCOUNT: $SERVICE_ACCOUNT"
    echo "APP_YAML_PATH: $APP_YAML_PATH"
    exit 1
fi

echo "Deploying pre-built Docker image from Google Artifact Registry to App Engine..."
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Version: $IMAGE_TAG"
echo "Service Account: $SERVICE_ACCOUNT"
echo "App YAML: $APP_YAML_PATH"

# Check that Auth0 environment variables are set
if [ -z "$AUTH0_ADDRESS_NO_DOMAIN" ] || [ -z "$AUTH0_AUDIENCE_NO_DOMAIN" ]; then
    echo "Error: Auth0 environment variables not set"
    exit 1
fi

echo "Substituting environment variables in app.yaml..."
TEMP_APP_YAML=$(mktemp)
envsubst < "$APP_YAML_PATH" > "$TEMP_APP_YAML"

# Deploy to App Engine using the substituted app.yaml
gcloud app deploy "$TEMP_APP_YAML" \
    --image-url="$IMAGE_NAME:$IMAGE_TAG" \
    --version="$IMAGE_TAG" \
    --service-account="$SERVICE_ACCOUNT" \
    --quiet

# Clean up
rm "$TEMP_APP_YAML"

echo "App Engine deployment completed successfully"