# Modal Release PRs

The household API Modal deployment uses a stable gateway app and versioned
worker apps. For calculation endpoints, the gateway routes requests to the
active `current` or `frontier` worker based on the request's top-level
`version` value.

The gateway image must stay lightweight: install only the dependencies needed
to accept HTTP requests, read the Modal manifest, and dispatch to worker Modal
functions. The worker image owns the full household API dependency set and must
preload country tax-benefit systems at image build time.

## PR Body Configuration

Configure Modal release behavior in the pull request body with a fenced YAML
block:

```yaml
modal_release:
  new_app_target: frontier
  promote_existing_frontier: true
  cleanup_target: retired
```

Allowed values:

- `new_app_target`: `frontier`, `current`, `both`, or `none`
- `promote_existing_frontier`: `true` or `false`
- `cleanup_target`: `none`, `retired`, `frontier`, or `current`

Normal PR validation rejects `cleanup_target: current` and
`cleanup_target: frontier`; active app cleanup must not be hidden inside a
regular code PR. `promote_existing_frontier: true` is only valid when
`new_app_target: frontier`.

Use this release shape for the normal weekly country-package release unless
the user explicitly asks for different current/frontier behavior:

```yaml
modal_release:
  new_app_target: frontier
  promote_existing_frontier: true
  cleanup_target: retired
```

This deploys the new worker to `frontier`, promotes the previous `frontier` to
`current`, and moves the previous `current` into the manifest's `retired`
history. This release shape uses `cleanup_target: retired`, so
apps in the retired history are stopped after the manifest is updated. Use
`cleanup_target: none` only when the user explicitly asks to preserve retired
worker apps after release.

Use this release shape when the newly built worker must become both `current`
and `frontier` in a single release:

```yaml
modal_release:
  new_app_target: both
  promote_existing_frontier: false
  cleanup_target: retired
```

This deploys one new worker app, writes the same app reference into both
`current` and `frontier`, and moves the previous active workers into the
manifest's `retired` history.

Do not use PR labels, branch names, model-specific tags, or title prefixes to
control Modal release behavior. The PR body YAML block is the source of truth.
The PR-body YAML block is the only automatic signal that a deployment should
promote, retire, clean up, or otherwise mutate the current/frontier manifest.
It is required when the PR changes a release-significant country package
version, meaning `policyengine_us` or `policyengine_uk` in `pyproject.toml`.
Code-only changes, including changes to Modal release code, must not require a
`modal_release` block unless those US or UK package versions also change.
The release workflow deploys from the finalized
`Update PolicyEngine Household API` versioning commit. When that commit has no
PR-body `modal_release` block, the workflow performs a code-only deploy: it
redeploys the active `current` and `frontier` worker apps already named in the
manifest, preserving each app's manifest-declared US/UK package versions, then
redeploys the gateway without changing the manifest. Ordinary push events do
not deploy Modal apps. Manual `workflow_dispatch` runs are explicit release
operations and use the weekly release shape by default.

The household API primary serving path is Modal-only. Do not add App Engine or
GCP traffic-promotion deployment steps to the release workflow, and do not route
primary household traffic through anything other than the Modal gateway. The one
deliberate exception is the Cloud Run failover path documented in
`modal-cloud-run-failover.md`: that path intentionally adds GCP Artifact
Registry, Docker image builds, and Cloud Run deploy steps to the release
workflow to stand up the standby gateway and fallback workers. Keep those steps
scoped to the failover gateway, the failover workers, and the GCS failover
manifest; they must not change how the Modal gateway serves current/frontier
traffic, and Modal remains the primary backend until an explicit traffic
cutover. The release workflow deploys the full Modal app set to the `staging`
Modal environment, runs the same deployed integration test suite as separate
matrix jobs for both `current` and `frontier`, then deploys the same release
config to the `main` Modal environment after all staging jobs pass. Each channel
is tested by channel name and by the exact US package version from
`/versions/us`. Google credentials in the release workflow are used for Cloud
SQL analytics database access, for syncing the Modal worker secret needed to
reach that database, and for deploying the Cloud Run failover gateway and
workers.

Only the US and UK package versions are release-significant. Do not include
Canada, Nigeria, or Israel package versions in Modal worker app names, manifest
package version references, or release validation. Those countries may still be
served by the worker, but their package versions must not control a Modal
release.

The canonical manifest schema version is `1`. Runtime code should validate that
stored manifests already match this schema; do not add legacy normalization to
the gateway, release updater, or active-app discovery paths. The manifest
rewrite command is the only bridge from older stored shapes: it copies the old
`current` and `frontier` app references into canonical schema version `1`,
drops retired history, and removes non-release package keys.

Manual workflow dispatch exposes the same `new_app_target`,
`promote_existing_frontier`, and `cleanup_target` settings as the PR-body YAML
block. The deploy workflow and Modal images use Python 3.13.

## Analytics Migrations

Modal releases use the same shared analytics database for `current` and
`frontier`. The release workflow runs `uv run alembic upgrade head` before
deploying a worker or updating the manifest.

Analytics migrations in normal Modal release PRs must be backward-compatible
with both active workers. Use expand/contract sequencing: add compatible schema
first, deploy through `frontier` and `current`, then remove obsolete schema only
after no active worker depends on it. Do not include table or column drops in a
normal Modal release PR.

Workers must validate that the database is at or after their minimum required
Alembic revision, not exactly equal to their bundled head. This lets an older
`current` worker keep running after a compatible `frontier` migration advances
the shared database.

Each manifest app reference records the worker's minimum required analytics
revision and the database revision observed after the release migration step.
The manifest must not include source commit metadata; use GitHub Actions and
Modal deployment history for deploy provenance.

## Request Routing

For `/calculate` and `/calculate_demo`, the Modal gateway reads the top-level
request field `version` and removes it before dispatching to the worker's
`HouseholdWorker.handle_household_request` Modal class method. Accepted
values are:

- omitted or `current`: route to the current worker
- `frontier`: route to the frontier worker
- an exact country package version that matches an active current/frontier
  worker for that country

Unknown versions return a 400 from the gateway.

Other endpoints are routed to the current worker and do not use
current/frontier version selection. Worker apps are internal Modal function
apps, not public WSGI web endpoints.

## Testing Expectations

When changing this system, include focused tests for:

- PR-body release config parsing and validation
- the separate PR checks for Modal release body config and Alembic migration
  compatibility
- changed-file detection for requiring the PR-body block
- manifest transitions across current, frontier, and retired apps
- gateway routing for current, frontier, exact package versions, and unknown
  versions
- analytics migration compatibility checks and destructive-migration rejection
