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
- `production.yaml.example` - Example production configuration
- `development.yaml.example` - Example development configuration  
- `local.yaml.example` - Example for fully local runs without external dependencies
- `example_values.env` - Example environment variables that can be programmatically read into a config template to allow the storing of sensitive values in a separate file; this will be covered later

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
# AUTH__ENABLED becomes auth.enabled
AUTH__ENABLED=true
```

Note: System environment variables starting with underscores are ignored.

### Method 2: Mounted Config File (Medium Priority)

You can mount an external configuration file to override the defaults:

#### Command Line
```bash
CONFIG_FILE=config/local.yaml make debug
```

#### Docker Run
```bash
# Mount a custom config file
docker run -v /path/to/your/config.yaml:/custom/config.yaml \
           -e CONFIG_FILE=/custom/config.yaml \
           policyengine/household-api
```

#### Docker Compose
```yaml
version: '3.13'
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
        - name: AUTH__ENABLED
          valueFrom:
            secretKeyRef:
              name: auth-value
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
  environment: Environment (can be any string)
  debug: Debug mode (true/false) - When true, if analytics enabled, uses local SQLite database instead of Cloud SQL

# User analytics (opt-in feature)
analytics:
  enabled: Whether to collect user analytics (default: false)
  database:
    connection_name: Google Cloud SQL connection name
    username: Database username
    password: Database password

auth:
  enabled: Whether authentication via auth0 is required (true/false)
  auth0:
    address: Auth0 domain (without https:// or trailing slash)
    audience: Auth0 audience/API identifier
    test_token: JWT token used only for pre-deployment GitHub Actions tests

ai:
  enabled: Whether AI features are enabled (true/false) (these features are only used in the alpha-mode AI explainer endpoint)
  anthropic:
    api_key: Anthropic API key

```

## User Analytics Configuration

User analytics is an **opt-in** feature that collects API usage metrics for monitoring and analysis. By default, analytics is **disabled**.

### Enabling Analytics

Analytics can be enabled in three ways:

1. **Via Configuration File** (Recommended for permanent enablement):
```yaml
# In your config file
analytics:
  enabled: true
  database:
    connection_name: your-project:region:instance
    username: analytics_user
    password: ${ANALYTICS_PASSWORD}  # Use env var for password
```

2. **Via Environment Variable**:
```bash
# Enable analytics
ANALYTICS__ENABLED=true

# Provide database credentials
USER_ANALYTICS_DB_CONNECTION_NAME=your-connection
USER_ANALYTICS_DB_USERNAME=your-username
USER_ANALYTICS_DB_PASSWORD=your-password
```

### What Data is Collected

When analytics is enabled, the following public data is collected per API request:
- Client ID (from JWT token)
- API version
- Endpoint accessed
- HTTP method
- Request content length
- Timestamp

All of these values are public and are used purely to establish usage rates.

### Privacy Considerations

- Analytics is **disabled by default**
- No request/response bodies are logged
- Only metadata about API usage is collected
- Data is stored in a separate analytics database

## Auth0 Authentication Configuration

Auth0 authentication is an **opt-in** feature that secures API endpoints with JWT token validation. By default, authentication is **disabled** to simplify local development and testing.

### Enabling Auth0

Auth0 can be enabled in three ways:

1. **Via Configuration File** (Recommended for permanent enablement):
```yaml
# In your config file
auth:
  enabled: true
  auth0:
    address: your-tenant.auth0.com
    audience: https://your-api-identifier
```

2. **Via Environment Variable**:
```bash
# Enable authentication
AUTH__ENABLED=true

# Provide Auth0 configuration
AUTH0_ADDRESS_NO_DOMAIN=your-tenant.auth0.com
AUTH0_AUDIENCE_NO_DOMAIN=https://your-api-identifier
```

### Protected Endpoints

When Auth0 is enabled, the following endpoints require valid JWT tokens:
- `/<country_id>/calculate` - Main calculation endpoint
- `/<country_id>/ai-analysis` - AI analysis endpoint (remains in alpha)

The following endpoints remain unprotected:
- `/` - Home endpoint
- `/liveness_check` - Health check endpoint
- `/readiness_check` - Readiness check endpoint
- `/<country_id>/calculate_demo` - Rate-limited demo endpoint (protected by rate limiting instead)

### Security Considerations

- Authentication is **disabled by default** for local development
- When enabled, all protected endpoints validate JWT tokens against Auth0's JWKS
- The Auth0 domain and audience must match the configured values

## Usage Examples

### Production Deployment (Current)

Currently in production, all configuration comes from environment variables:

```bash
# Via GitHub Actions secrets

# Auth0 configuration (opt-in)
AUTH__ENABLED=true  # Enable Auth0 authentication
AUTH0_ADDRESS_NO_DOMAIN=${{ secrets.AUTH0_ADDRESS_NO_DOMAIN }}
AUTH0_AUDIENCE_NO_DOMAIN=${{ secrets.AUTH0_AUDIENCE_NO_DOMAIN }}
AUTH0_TEST_TOKEN_NO_DOMAIN=${{ secrets.AUTH0_TEST_TOKEN_NO_DOMAIN }} # Used for local testing purposes

# Analytics configuration (opt-in)
ANALYTICS__ENABLED=true  # Enable user analytics
USER_ANALYTICS_DB_USERNAME=${{ secrets.USER_ANALYTICS_DB_USERNAME }}
USER_ANALYTICS_DB_PASSWORD=${{ secrets.USER_ANALYTICS_DB_PASSWORD }}
USER_ANALYTICS_DB_CONNECTION_NAME=${{ secrets.USER_ANALYTICS_DB_CONNECTION_NAME }}

# AI services
ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
```

### Local Development

Use environment variables to override specific settings:

```bash
docker run -e FLASK_DEBUG=1 \
           -e AUTH__ENABLED=false \    # Disable Auth0 for local dev
           -e ANALYTICS__ENABLED=false \ # Disable analytics for local dev
           -e AI__ENABLED=false \
           -e DATABASE__PROVIDER=sqlite \
           policyengine/household-api
```

#### Template Variable Substitution

The configuration loader supports template variable substitution using `${VAR}` or `$VAR` syntax in YAML files. This allows you to keep sensitive values in a separate file and reference them in your config without setting them as environment variables.

##### How It Works

1. Create a config values file (e.g., `config_values.env`) with your sensitive values:
```bash
# config_values.env
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_AUDIENCE=https://your-api.example.com
AUTH0_TOKEN=your-test-token
ANTHROPIC_API_KEY=your-api-key
ANALYTICS_PASSWORD=secure-password
```

2. Reference these in your config file using `${VAR}` or `$VAR` syntax:
```yaml
# config/local.yaml
auth:
  enabled: true
  auth0:
    address: ${AUTH0_DOMAIN}
    audience: ${AUTH0_AUDIENCE}
    test_bearer_token: ${AUTH0_TOKEN}

ai:
  enabled: true
  anthropic:
    api_key: $ANTHROPIC_API_KEY  # With or without brackets works

analytics:
  enabled: true
  database:
    password: ${ANALYTICS_PASSWORD}
```

3. Use the `CONFIG_VALUE_SETTINGS` environment variable to point to your values file:
```bash
CONFIG_VALUE_SETTINGS=config_values.env CONFIG_FILE=config/local.yaml make debug
```

##### Docker Usage

In Docker, you can mount both the config file and the values file:

```bash
docker run -v /path/to/config.yaml:/app/config/custom.yaml \
           -v /path/to/values.env:/app/config/values.env \
           -e CONFIG_FILE=/app/config/custom.yaml \
           -e CONFIG_VALUE_SETTINGS=/app/config/values.env \
           policyengine/household-api
```

Or with Docker Compose:
```yaml
version: '3.13'
services:
  household-api:
    image: policyengine/household-api
    volumes:
      - ./my-config.yaml:/app/config/custom.yaml
      - ./my-values.env:/app/config/values.env
    environment:
      - CONFIG_FILE=/app/config/custom.yaml
      - CONFIG_VALUE_SETTINGS=/app/config/values.env
```

##### Kubernetes Usage

With Kubernetes, you can use ConfigMaps or Secrets:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: household-api-values
stringData:
  values.env: |
    AUTH0_DOMAIN=your-domain.auth0.com
    AUTH0_AUDIENCE=https://your-api.example.com
    ANTHROPIC_API_KEY=your-api-key
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: household-api-config
data:
  config.yaml: |
    auth:
      enabled: true
      auth0:
        address: ${AUTH0_DOMAIN}
        audience: ${AUTH0_AUDIENCE}
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: api
        env:
        - name: CONFIG_FILE
          value: /config/config.yaml
        - name: CONFIG_VALUE_SETTINGS
          value: /secrets/values.env
        volumeMounts:
        - name: config
          mountPath: /config
        - name: values
          mountPath: /secrets
      volumes:
      - name: config
        configMap:
          name: household-api-config
      - name: values
        secret:
          secretName: household-api-values
```

##### Important Notes

- **Flask Auto-loading**: Flask automatically loads `.env` files when `python-dotenv` is installed and the `FLASK_DEBUG` environment variable is set to true. This will cause these values to override any external config files you specify, which may be undesirable for a given use case. To prevent this, either:
  - Name your values file something other than `.env` (e.g., `config_values.env`)
  - Set `FLASK_SKIP_DOTENV=1` when running Flask
  
- **Validation**: The loader validates that all referenced variables in the config file exist in the values file, providing clear error messages if any are missing

- **Format**: The values file uses standard `.env` format:
  - `KEY=value` pairs, one per line
  - Comments start with `#`
  - Empty lines are ignored
  - No quotes needed around values (they'll be included literally if present)

## Using ConfigLoader in Code

To use the configuration system in new code:

```python
from policyengine_household_api.utils import get_config_value

# Get nested configuration
auth_enabled = get_config_value("auth.enabled", False)
```

## Best Practices

1. **Never put secrets in config files** - Use environment variables for sensitive data
2. **Use mounted configs for structure** - Define your infrastructure layout in config files
3. **Use env vars for secrets** - Override sensitive values at runtime
4. **Version control your configs** - Keep config files in source control (without secrets)
5. **Environment-specific configs** - Have separate config files for dev/staging/prod
