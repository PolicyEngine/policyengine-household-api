# Monorepo Layout

The repository is a uv workspace: one `uv.lock` at the root, each shared lib
and deployable service its own package with its own `pyproject.toml`. The
root `pyproject.toml` is a virtual workspace root holding only tool
configuration and the dev dependency group.

## Members

| Directory | Package | Role |
|---|---|---|
| `libs/household-common` | `policyengine_household_common` | Light shared kernel: constants, config loader, pydantic models, observability, version routing, gateway core, release manifest/config, dispatch codecs. **No numpy, SQLAlchemy, modal, or country packages** — the slim writer image installs it, and hygiene tests enforce the boundary. |
| `libs/household-analytics` | `policyengine_household_analytics` | Analytics events, persistence, ORM, database setup; Alembic migration scripts ship inside the package. |
| `libs/household-api` | `policyengine_household_api` | The core Flask application (endpoints, country engine, auth, analytics producer). The published PyPI package; import path unchanged. |
| `projects/modal-api` | `policyengine_household_modal` | Modal worker/gateway/canary apps, image builders, release manifest CLIs. Never published. |
| `projects/cloud-run-failover-api` | `policyengine_household_failover` | Cloud Run gateway + fallback workers. Base closure = slim gateway; the `worker` extra pulls the core app. Never published. |
| `projects/analytics-api` | `policyengine_household_analytics_api` | The Cloud Run analytics writer + `alembic.ini`. Depends only on the analytics lib; heavy modules are structurally uninstallable in its closure. Never published. |

Dependency direction: `common ← analytics ← analytics-api`;
`common ← household-api ← modal-api / failover-api (worker extra)`.
Never import "up" this graph (e.g. nothing in `libs/` may import from
`projects/`; common imports nothing from any other member).

## Rules

- One version, lockstep, stamped on every member by `.github/bump_version.py`,
  which also rewrites the core package's exact pins on its sibling libs.
- PyPI receives three distributions per release, published in order:
  common → analytics → core. The service projects are never published
  (`Private :: Do Not Upload`).
- Install the workspace with `uv sync --all-packages` (what `make install`
  runs). `uv sync --package <member>` prunes the venv to one member's closure
  — CI and Docker builds use it; afterwards restore with `--all-packages`.
- Docker builds sync one member from the lockfile; every member's
  `pyproject.toml` must be COPYed into the build context even when not
  installed, because uv needs them to parse the workspace.
- Modal images cannot use `Image.uv_sync` (no workspace support); they export
  the member's locked closure with `uv export` and attach first-party
  packages as local sources (`projects/modal-api/.../images.py`).
- Keep lib `__init__.py` files free of imports. Issue #1603 (the analytics
  writer crash-looping on an eagerly imported numpy) is the reason most of
  this structure exists.
- Tests currently live at the repo root (`tests/`) and run in the fat
  all-packages environment, except `projects/analytics-api/tests`, which PR
  CI also runs in that member's slim closure. Colocating the rest of the
  tests with their members is a planned follow-up.
