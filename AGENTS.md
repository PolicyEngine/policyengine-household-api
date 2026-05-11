# Agent Instructions

These instructions apply repository-wide.

## Skills System

Canonical AI-facing engineering guidance lives under
`docs/engineering/skills/`. Use those files as the source of truth across
Codex, Claude, Copilot, and other AI tools.

When changing analytics database models or Alembic migrations, read
`docs/engineering/skills/database-migrations.md`.

When adding, moving, or reviewing tests, keep reusable mocks, patches, and setup
helpers in `tests/fixtures/` or the narrowest applicable `conftest.py`; test
files should focus on arranging inputs and asserting behavior.

## Pull Requests

Use plain descriptive PR titles without model-specific labels such as
`[codex]`, `[claude]`, or `[copilot]`.

Before sharing a PR, verify the branch has been pushed to the canonical
`PolicyEngine/policyengine-household-api` repository and that CI has been
checked.
