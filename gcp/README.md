# GCP container assets

This directory holds the container build assets for the household API's GCP
footprint. The production serving path is **Modal + Cloud Run**; App Engine has
been retired.

- `cloud_run/` — Dockerfiles and entrypoints for the Cloud Run services on the
  live serving path: the request `gateway`, the failover `worker`, and the
  `analytics_writer`. Built and deployed by `.github/workflows/deploy-staged.yml`
  (see `docs/engineering/skills/modal-cloud-run-failover.md`).
- `policyengine_household_api/Dockerfile.production` (+ `start.sh`) — the
  self-hosting / local-development image published to ghcr.io by
  `.github/workflows/publish-docker-image.yml`. It is a distribution artifact,
  not part of the deploy pipeline (see
  `docs/engineering/skills/docker-images.md`).

Do not add App Engine deployment assets (`app.yaml`, `dispatch.yaml`,
`gcloud app deploy`) here — the release workflow is Modal-only.
