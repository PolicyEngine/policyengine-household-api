# Agent Instructions

These instructions apply repository-wide.

## Skills system

Canonical AI-facing engineering guidance lives under
`docs/engineering/skills/`. Use those files as the source of truth across
Codex, Claude, Copilot, and other AI tools.

When moving code between workspace members, adding a workspace member, or
changing member dependencies, read
`docs/engineering/skills/monorepo-layout.md`.

When changing analytics database models or Alembic migrations, read
`docs/engineering/skills/database-migrations.md`.

When changing Modal current/frontier release behavior, PR release settings, or
deployment workflows, read `docs/engineering/skills/modal-release-prs.md`.

When changing Docker image publishing, image tags, or the published
Dockerfile, read `docs/engineering/skills/docker-images.md`.

When changing Cloud Run gateway failover, Cloud Run fallback workers, or
Modal-to-Cloud-Run fallback deployment workflows, read
`docs/engineering/skills/modal-cloud-run-failover.md`.

When adding, moving, or reviewing tests, read
`docs/engineering/skills/testing.md`.

Before opening, replacing, or sharing a pull request, read
`docs/engineering/skills/github-prs.md`.
