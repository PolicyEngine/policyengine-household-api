# Changelog

Partner-visible changes to the PolicyEngine Household API. For the full commit-level changelog (including internal refactors, dependency updates, and infrastructure changes that don't affect the request/response contract), see [`CHANGELOG.md`](https://github.com/PolicyEngine/policyengine-household-api/blob/main/CHANGELOG.md) in the repository.

## How to read this page

Entries are grouped into three categories:

- **Added** — new behavior that didn't exist before
- **Fixed** — behavior that disagreed with the documented contract or with the [PolicyEngine main API](https://policyengine.org/us/api), now corrected
- **Changed** — behavior that did work but works differently now

Each entry links to the pull request and includes the date the change shipped to production.

## Pinning a version

The hosted API always runs the latest release. If you need a specific model version for reproducibility, run the [self-hosted Docker image](index.md#self-hosted) and pin a tag:

```bash
docker run --rm -p 8080:8080 ghcr.io/policyengine/policyengine-household-api:1.634.8
```

The image tag matches the `model_version` returned in `policyengine_bundle` on every response, so you can confirm what's running.

## Recent releases

### Added: Year-keyed inputs on month-defined variables (PR #1490)

Year-keyed numeric inputs on MONTH-defined variables now distribute across the twelve months of the year as `V / 12`. Before, the engine silently ignored them and partners saw confusing zero results. The behavior now matches the [PolicyEngine main API](https://policyengine.org/us/api) and policyengine-core's `set_input_divide_by_period`.

Boolean, string, and enum year-keyed inputs broadcast unchanged across every month.

Mixed-shape requests — `{"2026": V, "2026-06": V'}` — treat the year value as the budget, subtract explicit monthly values, and split the remainder across the unset months. The API rejects only when every month is explicit AND the monthlies don't sum to the annual total.

See [Period keys](period-keys.md) for the full rules.

### Added: `warnings` array (PR #1490)

Responses now include a top-level `warnings` array when the API detects a request shape that may produce surprising numbers. The first warning surfaces partial monthly input paired with an annual output for the same year — the most common period-key pitfall.

The numeric `result` is unchanged. Warnings are informational.

See [Response format](response-format.md#the-warnings-array).

### Added: 400 on malformed period keys (PR #1490)

Period keys that don't parse as a year or month (e.g. `"not-a-period"`, `"2026/13"`) now return a 400 with the offending key, variable name, and entity. Before, the engine silently ignored the slot and returned a confusing zero.

See [Period keys](period-keys.md#what-the-api-rejects).

### Changed: Axes validation moved out of the compute path (PR #1488)

Requests with malformed `axes` now return a 400 from the validator instead of a 500 from the engine. The cap remains 10 entries × 100 count.

### Removed: CORS origin restrictions (PR #1488)

The API no longer restricts CORS by origin. Self-hosted deployments integrating from any domain work without a CORS preflight rejection.
