# Claude Instructions

These instructions apply repository-wide.

## Canonical Guidance

Repository-wide AI-facing engineering guidance lives in `AGENTS.md`.
Canonical skills live under `docs/engineering/skills/`.

Use those files as the source of truth. This file is a Claude adapter and should
stay thin; do not duplicate detailed testing, CI, formatting, migration, or
architecture rules here.

## Required Skill Lookup

When changing analytics database models or Alembic migrations, read
`docs/engineering/skills/database-migrations.md`.
