# Configuration Directory

This directory contains configuration files for the PolicyEngine Household API.

## Current Implementation Status

The application now has a `ConfigLoader` class (`policyengine_household_api/utils/config_loader.py`) that supports hierarchical configuration loading. While the system is ready, the application code still uses environment variables directly. Configuration files in this directory establish the structure for gradual migration.

## Configuration Priority

The `ConfigLoader` loads configuration from multiple sources in the following priority order (highest to lowest):

1. **Environment Variables** - Override everything
2. **Mounted Config File** - External configuration file (via `CONFIG_FILE` env var)
3. **Default Config** - Baked into the Docker image at `/app/config/default.yaml`

Environment variables always win, allowing you to override specific settings without changing config files.

## Files in this Directory

- `default.yaml` - Default configuration for local development (currently mostly empty/commented)
- `custom.yaml.example` - Example template for mounting custom configuration
- `production.yaml.example` - Example production configuration
- `development.yaml.example` - Example development configuration  
- `local.yaml.example` - Example for fully local runs without external dependencies

## Configuration Methods

### Method 1: Environment Variables (Highest Priority)

Environment variables override all other configuration sources. They work in two ways:

#### Explicit Mapping
Pre-defined environment variables that map to specific config paths:

```bash
# Database configuration
USER_ANALYTICS_DB_CONNECTION_NAME=my-connection
USER_ANALYTICS_DB_USERNAME=myuser
USER_ANALYTICS_DB_PASSWORD=secret

# Auth configuration
AUTH0_ADDRESS_NO_DOMAIN=my-auth0-domain
AUTH0_AUDIENCE_NO_DOMAIN=my-audience

# AI configuration
ANTHROPIC_API_KEY=sk-ant-...

# Debug mode
FLASK_DEBUG=1

# Server configuration
PORT=8080
```

#### Double Underscore Notation
Any environment variable with double underscores (`__`) is automatically mapped to nested config:

```bash
# DATABASE__HOST becomes database.host
DATABASE__HOST=localhost
DATABASE__PORT=3306

# AUTH__ENABLED becomes auth.enabled
AUTH__ENABLED=true

# SERVER__WORKERS becomes server.workers
SERVER__WORKERS=4
```

Note: System environment variables starting with underscores are ignored.

### Method 2: Mounted Config File (Medium Priority)

You can mount an external configuration file to override the defaults:

#### Docker Run
```bash
# Mount a custom config file
docker run -v /path/to/your/config.yaml:/custom/config.yaml \
           -e CONFIG_FILE=/custom/config.yaml \
           policyengine/household-api
```

#### Docker Compose
```yaml
version: '3.8'
services:
  household-api:
    image: policyengine/household-api
    volumes:
      - ./my-config.yaml:/app/config/custom.yaml
    environment:
      - CONFIG_FILE=/app/config/custom.yaml
      # Still provide secrets via env vars
      - DATABASE__PASSWORD=${DB_PASSWORD}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

#### Kubernetes ConfigMap
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: household-api-config
data:
  config.yaml: |
    database:
      provider: postgres
      host: postgres.default.svc.cluster.local
    auth:
      enabled: true
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: api
        image: policyengine/household-api
        env:
        - name: CONFIG_FILE
          value: /config/config.yaml
        - name: DATABASE__PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
        volumeMounts:
        - name: config
          mountPath: /config
      volumes:
      - name: config
        configMap:
          name: household-api-config
```

### Method 3: Default Config (Lowest Priority)

The default configuration is baked into the Docker image at `/app/config/default.yaml`. This provides sensible defaults for local development and serves as a fallback.

## Configuration Structure

```yaml
app:
  name: Application name (default: policyengine-household-api)
  environment: Environment (local/development/staging/production)
  debug: Debug mode (true/false)

database:
  provider: Database type (sqlite/mysql/postgres)
  connection_name: Cloud SQL connection name (for GCP)
  username: Database username
  password: Database password
  host: Database host
  port: Database port
  path: SQLite file path (for sqlite provider)
  pool_size: Connection pool size

storage:
  provider: Storage backend (local/gcs/s3)
  bucket: Storage bucket name (for cloud providers)
  path: Local storage path (for local provider)

auth:
  enabled: Whether authentication is required (true/false)
  provider: Auth provider (none/auth0/cognito)
  auth0:
    address: Auth0 domain
    audience: Auth0 audience

ai:
  enabled: Whether AI features are enabled (true/false)
  provider: AI service provider (none/anthropic/openai)
  anthropic:
    api_key: Anthropic API key
    model: Model name
    max_tokens: Maximum tokens
    temperature: Temperature setting

server:
  port: Server port (default: 8080)
  workers: Number of worker processes
  threads: Number of threads per worker
  timeout: Request timeout in seconds

logging:
  level: Log level (DEBUG/INFO/WARNING/ERROR)
  format: Log format (json/text)
```

## Usage Examples

### Production Deployment (Current)

Currently in production, all configuration comes from environment variables:

```bash
# Via GitHub Actions secrets
AUTH0_ADDRESS_NO_DOMAIN=${{ secrets.AUTH0_ADDRESS_NO_DOMAIN }}
AUTH0_AUDIENCE_NO_DOMAIN=${{ secrets.AUTH0_AUDIENCE_NO_DOMAIN }}
USER_ANALYTICS_DB_USERNAME=${{ secrets.USER_ANALYTICS_DB_USERNAME }}
USER_ANALYTICS_DB_PASSWORD=${{ secrets.USER_ANALYTICS_DB_PASSWORD }}
USER_ANALYTICS_DB_CONNECTION_NAME=${{ secrets.USER_ANALYTICS_DB_CONNECTION_NAME }}
ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
```

### Local Development

Use environment variables to override specific settings:

```bash
docker run -e FLASK_DEBUG=1 \
           -e AUTH__ENABLED=false \
           -e AI__ENABLED=false \
           -e DATABASE__PROVIDER=sqlite \
           policyengine/household-api
```

### Custom Cloud Provider

Mount a complete custom configuration:

```bash
# Create custom config
cat > aws-config.yaml <<EOF
database:
  provider: postgres
  host: my-rds-instance.amazonaws.com
storage:
  provider: s3
  bucket: my-household-data
auth:
  provider: cognito
  pool_id: us-east-1_xxxxx
EOF

# Run with custom config
docker run -v $(pwd)/aws-config.yaml:/app/config/aws.yaml \
           -e CONFIG_FILE=/app/config/aws.yaml \
           -e DATABASE__PASSWORD="${RDS_PASSWORD}" \
           policyengine/household-api
```

## Migration Status

### Phase 1 (Current)
- ✅ `ConfigLoader` class implemented
- ✅ Hierarchical configuration loading working
- ✅ Environment variable mapping functional
- ✅ Docker image includes default config
- ⏳ Application code still uses `os.getenv()` directly

### Phase 2 (Next Steps)
- Gradually update application code to use `get_config_value()` instead of `os.getenv()`
- Move non-sensitive defaults to config files
- Keep sensitive values in environment variables

### Phase 3 (Future)
- Configuration files become primary source
- Environment variables used only for secrets and overrides
- Full configuration validation with Pydantic models

## Using ConfigLoader in Code

To use the configuration system in new code:

```python
from policyengine_household_api.utils import get_config_value

# Get a configuration value with a default
db_provider = get_config_value("database.provider", "sqlite")

# Get nested configuration
auth_enabled = get_config_value("auth.enabled", False)
```

## Best Practices

1. **Never put secrets in config files** - Use environment variables for sensitive data
2. **Use mounted configs for structure** - Define your infrastructure layout in config files
3. **Use env vars for secrets** - Override sensitive values at runtime
4. **Version control your configs** - Keep config files in source control (without secrets)
5. **Environment-specific configs** - Have separate config files for dev/staging/prod

## Debugging Configuration

To see what configuration is being loaded, set the log level to DEBUG:

```bash
docker run -e LOGGING__LEVEL=DEBUG policyengine/household-api
```

The application will log:
- Which config files were loaded
- Which environment variables were applied
- Any errors in loading configuration files