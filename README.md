# PolicyEngine API Light

A lighter version of the PolicyEngine API that only runs the `calculate` endpoint. To debug locally, run `make debug`. Then in separate terminals runs `redis-server` and `python policyengine_api_light/worker.py` for the long-running tasks. You'll need to make sure `redis` is installed.

## Development rules

1. Every endpoint should return a JSON object with at least a "status" and "message" field.
