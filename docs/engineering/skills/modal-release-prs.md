# Modal Release PRs

The household API Modal deployment uses a stable gateway app and versioned
worker apps. The gateway routes requests to the active `current` or `frontier`
worker based on the request's top-level `version` value.

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

## Request Routing

For `/calculate`, `/calculate_demo`, and `/ai-analysis`, the Modal gateway reads
the top-level request field `version` and removes it before proxying to the
worker. Accepted values are:

- omitted or `current`: route to the current worker
- `frontier`: route to the frontier worker
- an exact country package version that matches an active current/frontier
  worker for that country

Unknown versions return a 400 from the gateway.

## Testing Expectations

When changing this system, include focused tests for:

- PR-body release config parsing and validation
- changed-file detection for requiring the PR-body block
- manifest transitions across current, frontier, and retired apps
- gateway routing for current, frontier, exact package versions, and unknown
  versions

