#!/bin/bash

# Verify that the Docker image was successfully pushed to GitHub Container Registry
set -e

# Get the generated tags from the metadata action
GENERATED_TAGS="${GENERATED_TAGS}"

if [ -z "$GENERATED_TAGS" ]; then
    echo "Error: GENERATED_TAGS environment variable not set"
    exit 1
fi

echo "Verifying image was pushed to Google Container Registry..."
echo "Generated tags: $GENERATED_TAGS"

# Try to pull using the first generated tag
FIRST_TAG=$(echo "$GENERATED_TAGS" | tr ' ' '\n' | head -1)

if [ -z "$FIRST_TAG" ]; then
    echo "Error: No tags found in GENERATED_TAGS"
    exit 1
fi

echo "Pulling first tag: $FIRST_TAG"
docker pull "$FIRST_TAG"

if [ $? -eq 0 ]; then
    echo "Image successfully pushed and can be pulled"
else
    echo "Failed to pull image"
    exit 1
fi
