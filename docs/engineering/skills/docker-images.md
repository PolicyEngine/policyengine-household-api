# Docker Images

The household API publishes Docker images to
`ghcr.io/policyengine/policyengine-household-api` as a distribution artifact
for self-hosting and local development. Image publishing is not deployment:
the hosted API runs only on Modal (see `modal-release-prs.md`), and the
publish workflow must never gate, modify, or participate in Modal releases.

## Tag scheme

| Tag | Meaning |
| --- | --- |
| `us-<version>` | Exact policyengine-us version baked in (e.g. `us-1.726.0`) |
| `current` | Same model version the hosted gateway's `current` channel serves |
| `frontier` | Same model version as the hosted `frontier` channel |
| `latest` | Alias of `current` |
| `<api-version>` | household-api release that built the image (e.g. `0.21.4`) |
| `sha-<commit>` | Release commit the image was built from |

Channel tags are floating pointers, repointed weekly. They always carry the
same model package versions as the hosted channels — `frontier` stays ahead
of (or, after a `both`-target release, equal to) `current` exactly as the
gateway manifest does; the publisher mirrors the manifest and never imposes
its own ordering.

The channel contract is about model package versions, not API-layer code.
A promoted `current` image keeps the API code it was built with as
`frontier`, matching the hosted worker, which is promoted without redeploy.
One known asymmetry: a code-only release redeploys both hosted workers with
new API code but only rebuilds the pyproject-pinned (frontier) image, so the
`current` image's API code can lag its worker until the next weekly
promotion; model outputs are unaffected. Force-rebuild an exact tag with a
manual `workflow_dispatch` run if this ever matters.

## How publishing works

`.github/workflows/publish-docker-image.yml` runs after each successful
push-triggered `Release to Modal` run. It checks out the release commit and:

1. Builds the exact-version image from `uv.lock` and pushes `us-<version>`,
   `<api-version>`, and `sha-<commit>` tags (linux/amd64 + linux/arm64).
2. After the build finishes, re-reads the live gateway `/versions/us`
   endpoint — the source of truth for channel state — and repoints `current`,
   `latest`, and `frontier` at the matching exact-version images with
   `docker buildx imagetools create` (a registry-level retag, no rebuild).
   Channel state is read at this point, not before the slow build, and only
   channels whose exact-version image is already published are repointed, so a
   release that lands mid-build never moves a channel tag backward.
3. Backfills any channel version whose exact-version image does not exist
   yet, using the `POLICYENGINE_US_VERSION` build arg. Backfilled images
   carry the release commit's API code, which may be newer than the code the
   corresponding Modal worker runs.

Reading channel state from the gateway (instead of recomputing the release
config) keeps tags correct across code-only releases and manual Modal
releases. Manual `workflow_dispatch` runs of `Release to Modal` do not
trigger publishing, mirroring the PyPI publish behavior; run the publish
workflow manually with `sync_channel_tags: true` afterwards if needed.

Publish runs queue one deep per the workflow's concurrency group, so if
several releases land back to back, an intermediate release's run can be
superseded: channel tags self-heal on the next run, but that release's
`sha-<commit>` and `<api-version>` tags are never published. If a versioned
tag is missing, recover with a manual `workflow_dispatch` run.

## Publishing an arbitrary model version

Run the `Publish Docker image` workflow manually with
`policyengine_us_version` set to any version on PyPI. This publishes only the
`us-<version>` tag and never touches channel tags. The pairing of current API
code with an arbitrary model version is best-effort and not covered by CI.

Anyone can build the same thing locally without registry access:

```bash
docker build -f gcp/policyengine_household_api/Dockerfile.production \
  --build-arg POLICYENGINE_US_VERSION=1.725.0 -t household-api:us-1.725.0 .
```

## Constraints

- Do not add image publishing steps to `deploy-staged.yml`; the release
  workflow stays Modal-only.
- The publish workflow uses only the built-in `GITHUB_TOKEN` with
  `packages: write`. Do not add registry credentials or other secrets.
- A container serves exactly one model version. The hosted API's
  request-body `version` routing is a Modal gateway feature and does not
  exist in these images.
- `gcp/policyengine_household_api/Dockerfile.production` is the only
  published Dockerfile. `docker/Dockerfile.api` is the docker-compose dev
  image and is not published.
