# PolicyEngine API Light

A lighter version of the PolicyEngine API that only runs the `calculate` endpoint. To debug locally, run `make debug`. 

## Development rules

1. Every endpoint should return a JSON object with at least a "status" and "message" field.
