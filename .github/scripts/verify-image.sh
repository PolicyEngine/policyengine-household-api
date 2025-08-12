#!/bin/bash

# Verify Docker image exists in GitHub Container Registry
set -e

# Get image name and tag from environment variables
IMAGE_NAME="${IMAGE_NAME}"
IMAGE_TAG="${IMAGE_TAG}"

if [ -z "$IMAGE_NAME" ] || [ -z "$IMAGE_TAG" ]; then
    echo "Error: IMAGE_NAME and IMAGE_TAG environment variables must be set"
    exit 1
fi

echo "Verifying image exists in GitHub Container Registry..."
echo "Image: $IMAGE_NAME:$IMAGE_TAG"

# Pull the image to verify it exists
docker pull "$IMAGE_NAME:$IMAGE_TAG"

echo "Image verified and ready for deployment"
