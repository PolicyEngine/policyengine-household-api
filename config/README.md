# Configuration Directory

This directory contains configuration files for the PolicyEngine Household API.

## Current State

The application currently uses environment variables for all configuration. These configuration files are placeholders that establish the structure for future migration to a file-based configuration system.

## Files

- `default.yaml` - Default configuration for local development (currently empty placeholders)
- `production.yaml.example` - Example production configuration (not used in deployment)
- `development.yaml.example` - Example development configuration

## Migration Plan

The configuration system will be migrated gradually:

1. **Phase 1 (Current)**: All configuration via environment variables
2. **Phase 2**: Configuration files with environment variable overrides
3. **Phase 3**: Configuration files as primary source, env vars for secrets only

## Configuration Structure

```yaml
app:
  name: Application name
  environment: Environment (local/development/staging/production)

database:
  provider: Database type (sqlite/mysql/postgres)
  # Connection details

storage:
  provider: Storage backend (local/gcs/s3)
  # Provider-specific settings

auth:
  enabled: Whether authentication is required
  provider: Auth provider (none/auth0/cognito)
  # Provider-specific settings

ai:
  enabled: Whether AI features are enabled
  provider: AI service provider (none/anthropic/openai)
  # Provider-specific settings

server:
  port: Server port
  workers: Number of worker processes
  timeout: Request timeout in seconds

logging:
  level: Log level (DEBUG/INFO/WARNING/ERROR)
  format: Log format (json/text)
```

## Environment Variable Mapping

When migrated, environment variables will map to configuration as follows:

- `FLASK_DEBUG` → `app.debug`
- `USER_ANALYTICS_DB_CONNECTION_NAME` → `database.connection_name`
- `USER_ANALYTICS_DB_USERNAME` → `database.username`
- `USER_ANALYTICS_DB_PASSWORD` → `database.password`
- `AUTH0_ADDRESS_NO_DOMAIN` → `auth.auth0.address`
- `AUTH0_AUDIENCE_NO_DOMAIN` → `auth.auth0.audience`
- `ANTHROPIC_API_KEY` → `ai.anthropic.api_key`

## Usage (Future)

Once migration is complete:

### Local Development
```bash
# Use default.yaml automatically
python -m policyengine_household_api.api

# Or specify a config file
CONFIG_FILE=config/development.yaml python -m policyengine_household_api.api
```

### Docker
```bash
# Mount custom config
docker run -v $(pwd)/my-config.yaml:/app/config/active.yaml household-api

# Or use environment variable to specify config location
docker run -e CONFIG_FILE=/app/config/production.yaml household-api
```

### Production
Environment variables will override config file values for sensitive data:
```bash
# Config file provides structure, env vars provide secrets
DATABASE__PASSWORD=secret CONFIG_FILE=production.yaml python -m app
```