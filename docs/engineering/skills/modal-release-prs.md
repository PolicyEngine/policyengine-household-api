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
  cleanup_target: none
```

Allowed values:

- `new_app_target`: `frontier`, `current`, or `none`
- `promote_existing_frontier`: `true` or `false`
- `cleanup_target`: `none`, `retired`, `frontier`, or `current`

Normal PR validation rejects `cleanup_target: current` and
`cleanup_target: frontier`; active app cleanup must not be hidden inside a
regular code PR. `promote_existing_frontier: true` is only valid when
`new_app_target: frontier`.

Use the default weekly release shape unless the user explicitly asks for a
different deployment behavior:

```yaml
modal_release:
  new_app_target: frontier
  promote_existing_frontier: true
  cleanup_target: none
```

This deploys the new worker to `frontier`, promotes the previous `frontier` to
`current`, and moves the previous `current` into the manifest's `retired`
history. Retired apps are not deleted unless `cleanup_target: retired` is
explicitly configured.

Do not use PR labels, branch names, model-specific tags, or title prefixes to
control Modal release behavior. The PR body YAML block is the source of truth.
The release workflow deploys from the finalized
`Update PolicyEngine Household API` versioning commit; ordinary push events do
not deploy Modal apps. Manual `workflow_dispatch` runs use the default weekly
release shape.

The household API deploy pipeline is Modal-only. Do not add App Engine, GCP
Artifact Registry, Docker image, or GCP traffic-promotion deployment steps to
the release workflow. The release workflow deploys the full Modal app set to
the `staging` Modal environment, runs deployed integration tests against active
`current` and `frontier` channels, then deploys the same release config to the
`main` Modal environment. Google credentials in the release workflow are only
for Cloud SQL analytics database access and for syncing the Modal worker secret
needed to reach that database.

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

## Request Routing

For `/calculate` and `/calculate_demo`, the Modal gateway reads the top-level
request field `version` and removes it before dispatching to the worker's
`handle_household_request` Modal function. Accepted values are:

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
