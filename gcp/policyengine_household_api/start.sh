#!/bin/bash
set -e

# Set the port to use
PORT=${PORT:-8080}

# Start the API
exec gunicorn -b :$PORT policyengine_household_api.api --timeout 300 --workers 2