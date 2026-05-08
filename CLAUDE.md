# PolicyEngine Household API Guidance

## Database Migrations

This project uses Alembic for analytics database migrations. See
`.claude/skills/database-migrations.md` for the detailed workflow.

Key rules:

- All analytics schema changes go through Alembic migrations.
- After modifying an analytics model, create the migration with
  `uv run alembic revision --autogenerate -m "Description"`.
- AI agents must read and verify the generated migration before applying it.
- Do not hand-author schema-change migrations. The only exception is a baseline
  migration for schema that already exists in production when that baseline is
  notably easier to represent by hand.
- Apply migrations with `uv run alembic upgrade head`.
