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
# Define environment variables to set
declare -A ENV_VARS=(
    ["AUTH0_ADDRESS_NO_DOMAIN"]="$AUTH0_ADDRESS_NO_DOMAIN"
    ["AUTH0_AUDIENCE_NO_DOMAIN"]="$AUTH0_AUDIENCE_NO_DOMAIN"
    ["USER_ANALYTICS_DB_USERNAME"]="$USER_ANALYTICS_DB_USERNAME"
    ["USER_ANALYTICS_DB_PASSWORD"]="$USER_ANALYTICS_DB_PASSWORD"
    ["USER_ANALYTICS_DB_CONNECTION_NAME"]="$USER_ANALYTICS_DB_CONNECTION_NAME"
    ["ANTHROPIC_API_KEY"]="$ANTHROPIC_API_KEY"
)

# Deploy to App Engine using the pre-built image
gcloud app deploy "$APP_YAML_PATH" \
    --image-url="$IMAGE_NAME:$IMAGE_TAG" \
    --version="$IMAGE_TAG" \
    --service-account="$SERVICE_ACCOUNT" \
    --quiet

echo "App Engine deployment completed successfully"
