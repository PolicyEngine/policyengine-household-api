# Engineering Skills

This directory is the canonical source for AI-facing engineering rules.

Tool-specific instruction files such as `AGENTS.md`, `CLAUDE.md`, and
`.github/copilot-instructions.md` should point here instead of duplicating
implementation-specific guidance. When a rule changes, update the skill here
first, then keep adapters thin.

Current skills:

- `database-migrations.md`: Alembic and analytics database migration rules.
- `github-prs.md`: same-repository PR workflow, PR head verification, changelog
  expectations, and title conventions.
- `testing.md`: test layout, fixture scope, reusable mock/patch placement, and
  verification expectations.
