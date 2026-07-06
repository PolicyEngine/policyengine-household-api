# analytics-api

The Cloud Run analytics writer service: receives calculate-analytics events
dispatched by Cloud Tasks at `/internal/analytics/calculate/write`, validates
them, and persists analytics rows. Owns the Alembic runner configuration
(`alembic.ini`); the migration scripts ship inside
`policyengine-household-analytics`.

Never published. Its dependency closure deliberately excludes numpy, country
model packages, and modal — enforced by the isolation test in `tests/` when
run in this member's own environment
(`uv sync --package policyengine-household-analytics-api`).
