# Docker guidance

This directory holds the container build assets for the household API. The
production serving path is Modal + Cloud Run, but the API image is also
published for **self-hosting and local development**, so build guidance lives
here. (App Engine has been retired — do not add App Engine deployment assets,
`dispatch.yaml`, or `gcloud app deploy` here.)

## Images

- `policyengine_household_api/Dockerfile.production` (+ `start.sh`) — the
  self-hostable API image, published to ghcr.io by
  `.github/workflows/publish-docker-image.yml`. Each image serves exactly one
  model version; the hosted API's request-body `version` routing is a Modal
  gateway feature and is not part of these images.
- `cloud_run/` — Dockerfiles and entrypoints for the Cloud Run services on the
  live serving path (`gateway`, failover `worker`, `analytics_writer`), built
  and deployed by `.github/workflows/deploy-staged.yml`.

## Building the API image

Anyone can build the self-hostable image locally, without registry access.
Pass the model version you want via the `POLICYENGINE_US_VERSION` build arg:

```bash
docker build -f gcp/policyengine_household_api/Dockerfile.production \
  --build-arg POLICYENGINE_US_VERSION=1.725.0 \
  -t household-api:us-1.725.0 .
```

This is a uv workspace, so image builds sync one member from the root lockfile
and expect every member's `pyproject.toml` in the build context. For published
tag conventions (channel vs `us-<version>` vs `sha-<commit>`), building an
arbitrary model version, and the full workspace-build notes, see
`docs/engineering/skills/docker-images.md`.
