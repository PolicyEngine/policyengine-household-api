# PolicyEngine Household API 

A version of the PolicyEngine API that runs the `calculate` endpoint over household object. To debug locally, run `make debug`. 

## Local development with Docker Compose

To run this app locally via Docker Compose:

```
% make docker-build
% make docker-run
```

and point your browser at http://localhost:8080 to access the API.

To develop the code locally, you will want to instead start only the Redis docker container and a one-off
API container, with your local filesystem mounted into the running docker container.

```
% make services-start
% make docker-console
```

Then inside the container, start the Flask service:

```
policyapi@[your-docker-id]:/code$ make debug
```

and point your browser at http://localhost:8080 to access the API.

## Development rules

1. Every endpoint should return a JSON object with at least a "status" and "message" field.

Please note that we do not support branched operations at this time.
