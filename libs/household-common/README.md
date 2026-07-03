# policyengine-household-common

Shared kernel for the PolicyEngine Household API services: constants, config
loading, pydantic models, observability integration, version routing, release
manifest handling, and dispatch codecs.

This package deliberately keeps a light dependency closure — no numpy, no
SQLAlchemy, no country model packages, no modal — because the slim analytics
writer image installs it. Do not add heavy imports at module level; see the
repository's `docs/engineering/` guidance before extending it.

Published to PyPI because `policyengine-household-api` depends on it. It is
not a standalone product; its API follows the needs of the Household API
services.
