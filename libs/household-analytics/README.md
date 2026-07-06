# policyengine-household-analytics

Analytics contract and persistence for the PolicyEngine Household API: the
calculate-analytics event schema, SQLAlchemy ORM models, analytics database
setup, and the Alembic migration scripts (shipped as package data).

The slim Cloud Run analytics writer installs this lib, so its dependency
closure deliberately excludes numpy, country model packages, and modal.

Published to PyPI because `policyengine-household-api` depends on it. It is
not a standalone product; its API follows the needs of the Household API
services.
