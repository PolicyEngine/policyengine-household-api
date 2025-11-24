#!/bin/bash
# Environment variables
PORT="${PORT:-8080}"
WORKER_COUNT="${WORKER_COUNT:-3}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Start the API
gunicorn -b :"$PORT" policyengine_household_api.api --timeout 300 --workers 5 --preload &

# Keep the script running and handle shutdown gracefully
trap "pkill -P $$; exit 1" INT TERM

wait
