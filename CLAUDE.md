# Claude Instructions

These instructions apply repository-wide.

## Canonical Guidance

Repository-wide AI-facing engineering guidance lives in `AGENTS.md`.
Canonical skills live under `docs/engineering/skills/`.

Use those files as the source of truth. This file is a Claude adapter and should
stay thin; do not duplicate detailed testing, CI, formatting, migration, or
architecture rules here.

## Required Skill Lookup

Before opening, replacing, or sharing a PR, read
`docs/engineering/skills/github-prs.md`.

When changing analytics database models or Alembic migrations, read
`docs/engineering/skills/database-migrations.md`.

When changing Modal current/frontier release behavior, PR release settings, or
deployment workflows, read `docs/engineering/skills/modal-release-prs.md`.

When changing Cloud Run gateway failover, Cloud Run fallback workers, or
Modal-to-Cloud-Run fallback deployment workflows, read
`docs/engineering/skills/modal-cloud-run-failover.md`.

When adding, moving, or reviewing tests, read
`docs/engineering/skills/testing.md`.
