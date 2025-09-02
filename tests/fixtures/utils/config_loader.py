"""
Fixtures for config loader unit tests.
"""

import tempfile
import yaml
import os
from pathlib import Path
from typing import Dict, Any
import pytest


# Sample configuration data constants
DEFAULT_CONFIG_DATA = {
    "app": {
        "name": "policyengine-household-api",
        "environment": "default",
        "debug": False,
    },
    "database": {"provider": "sqlite", "path": ":memory:"},
    "server": {"port": 8080, "workers": 1, "timeout": 300},
}

EXTERNAL_CONFIG_DATA = {
    "app": {"environment": "external", "debug": True},
    "database": {"provider": "mysql", "host": "external-host", "port": 3306},
}

CUSTOM_CONFIG_DATA = {
    "app": {"environment": "custom"},
    "database": {
        "provider": "postgres",
        "host": "custom-host",
        "port": 5432,
        "database": "custom_db",
    },
    "auth": {"enabled": True, "provider": "auth0"},
    "ai": {"enabled": True, "provider": "anthropic"},
}

# Environment variable test data
ENV_VAR_TEST_DATA = {
    # Traditional PolicyEngine env vars
    "FLASK_DEBUG": "1",
    "USER_ANALYTICS_DB_CONNECTION_NAME": "test-connection-name",
    "USER_ANALYTICS_DB_USERNAME": "test-username",
    "USER_ANALYTICS_DB_PASSWORD": "test-password",
    "AUTH0_ADDRESS_NO_DOMAIN": "test-auth0-address",
    "AUTH0_AUDIENCE_NO_DOMAIN": "test-auth0-audience",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
    "PORT": "9090",
}

# Double underscore notation test data
DOUBLE_UNDERSCORE_ENV_VARS = {
    "DATABASE__HOST": "env-db-host",
    "DATABASE__PORT": "5432",
    "DATABASE__POOL_SIZE": "20",
    "SERVER__WORKERS": "4",
    "SERVER__THREADS": "2",
    "AUTH__ENABLED": "true",
    "AUTH__PROVIDER": "cognito",
    "LOGGING__LEVEL": "DEBUG",
    "LOGGING__FORMAT": "json",
}

# Type conversion test data
TYPE_CONVERSION_TEST_CASES = [
    # Boolean conversions
    ("true", True),
    ("True", True),
    ("TRUE", True),
    ("yes", True),
    ("Yes", True),
    ("1", True),
    ("false", False),
    ("False", False),
    ("FALSE", False),
    ("no", False),
    ("No", False),
    ("0", False),
    # Integer conversions
    ("123", 123),
    ("-456", -456),
    ("0", False),  # Note: "0" converts to False, not 0
    # Float conversions
    ("3.14", 3.14),
    ("-2.5", -2.5),
    ("1.0", 1.0),
    # String (no conversion)
    ("hello", "hello"),
    ("true_but_not_bool", "true_but_not_bool"),
    ("123.456.789", "123.456.789"),  # Not a valid float
]


@pytest.fixture
def temp_default_config():
    """Create a temporary default config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(DEFAULT_CONFIG_DATA, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_external_config():
    """Create a temporary external config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(EXTERNAL_CONFIG_DATA, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_custom_config():
    """Create a temporary custom config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(CUSTOM_CONFIG_DATA, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_empty_config():
    """Create a temporary empty config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("# Empty config file\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_invalid_yaml_config():
    """Create a temporary config file with invalid YAML."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            "invalid: yaml: content:\n  - this is not: valid\n    yaml syntax"
        )
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def clean_env(monkeypatch):
    """
    Fixture to ensure a clean environment for each test.
    Returns the monkeypatch object for setting env vars.
    """
    import os

    # Remove any CONFIG_FILE env var
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    # Remove all test env vars if they exist
    for env_var in ENV_VAR_TEST_DATA:
        monkeypatch.delenv(env_var, raising=False)

    for env_var in DOUBLE_UNDERSCORE_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    # Remove any environment variables that might be picked up by the config loader
    # This includes PolicyEngine-specific vars that might be set in the dev environment
    policyengine_env_vars = [
        "USER_ANALYTICS_DB_CONNECTION_NAME",
        "USER_ANALYTICS_DB_USERNAME",
        "USER_ANALYTICS_DB_PASSWORD",
        "AUTH0_ADDRESS_NO_DOMAIN",
        "AUTH0_AUDIENCE_NO_DOMAIN",
        "ANTHROPIC_API_KEY",
        "FLASK_DEBUG",
        "PORT",
    ]

    for env_var in policyengine_env_vars:
        monkeypatch.delenv(env_var, raising=False)

    # Also remove any env vars with double underscores that might interfere
    # We need to be careful not to remove system-critical vars
    current_env_vars = list(os.environ.keys())
    for env_var in current_env_vars:
        if "__" in env_var and not env_var.startswith("__"):
            # Only remove non-system double underscore vars
            # System vars typically start with __ (like __CF_USER_TEXT_ENCODING)
            monkeypatch.delenv(env_var, raising=False)

    return monkeypatch


@pytest.fixture
def config_with_env_vars(clean_env):
    """Set up traditional PolicyEngine environment variables."""
    for key, value in ENV_VAR_TEST_DATA.items():
        clean_env.setenv(key, value)
    return clean_env


@pytest.fixture
def config_with_double_underscore(clean_env):
    """Set up double underscore notation environment variables."""
    for key, value in DOUBLE_UNDERSCORE_ENV_VARS.items():
        clean_env.setenv(key, value)
    return clean_env


@pytest.fixture
def config_with_mixed_env_vars(clean_env):
    """Set up both traditional and double underscore env vars."""
    for key, value in ENV_VAR_TEST_DATA.items():
        clean_env.setenv(key, value)
    for key, value in DOUBLE_UNDERSCORE_ENV_VARS.items():
        clean_env.setenv(key, value)
    return clean_env


# CONFIG_VALUE_SETTINGS fixtures
@pytest.fixture
def temp_valid_config_values_file():
    """Create a temporary valid config values file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("# This is a comment\n")
        f.write("AUTH0_ADDRESS=example.auth0.com\n")
        f.write("AUTH0_AUDIENCE=https://api.example.com\n")
        f.write("DB_PASSWORD=secret123\n")
        f.write("\n")  # Empty line
        f.write("ANOTHER_VAR=value_with_equals=sign\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_config_with_variables():
    """Create a temporary config file with variable references."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            """
auth:
  address: ${AUTH0_ADDRESS}
  audience: $AUTH0_AUDIENCE
database:
  password: ${DB_PASSWORD}
special: ${ANOTHER_VAR}
        """
        )
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_missing_vars_config_values():
    """Create config values file missing some variables."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("AUTH0_ADDRESS=example.auth0.com\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_config_with_missing_var():
    """Create config file with a missing variable reference."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            """
auth:
  address: ${AUTH0_ADDRESS}
  audience: ${MISSING_VAR}
        """
        )
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_invalid_format_values_file():
    """Create config values file with invalid format."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("VALID_KEY=valid_value\n")
        f.write("invalid-key=value\n")  # Invalid: contains hyphen
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_invalid_key_number_values_file():
    """Create config values file with key starting with number."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("123_KEY=value\n")  # Invalid: starts with number
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_duplicate_keys_values_file():
    """Create config values file with duplicate keys."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("DUPLICATE_KEY=first_value\n")
        f.write("OTHER_KEY=other_value\n")
        f.write("DUPLICATE_KEY=second_value\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_config_with_duplicate_key():
    """Create config file referencing duplicate key."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("test: ${DUPLICATE_KEY}")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_empty_values_file():
    """Create empty config values file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("# Just comments\n")
        f.write("\n")
        f.write("   \n")  # Whitespace only
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_complex_values_file():
    """Create config values file with complex values."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("URL_WITH_QUERY=https://example.com?param=value&other=123\n")
        f.write('JSON_STRING={"key": "value", "number": 123}\n')
        f.write("PATH_WITH_SPACES=/path/to/some file.txt\n")
        f.write("EMPTY_VALUE=\n")
        f.write('VALUE_WITH_QUOTES="quoted value"\n')
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_config_with_complex_values():
    """Create config file with complex value references."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            """
url: ${URL_WITH_QUERY}
json: ${JSON_STRING}
path: ${PATH_WITH_SPACES}
empty: ${EMPTY_VALUE}
quoted: ${VALUE_WITH_QUOTES}
        """
        )
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_realistic_values_file():
    """Create realistic config values file for integration testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("AUTH0_ADDRESS_NO_DOMAIN=policyengine.uk.auth0.com\n")
        f.write(
            "AUTH0_AUDIENCE_NO_DOMAIN=https://household.api.policyengine.org\n"
        )
        f.write("AUTH0_TEST_TOKEN_NO_DOMAIN=test-jwt-token\n")
        f.write("USER_ANALYTICS_DB_CONNECTION_NAME=project:region:instance\n")
        f.write("USER_ANALYTICS_DB_USERNAME=analytics_user\n")
        f.write("USER_ANALYTICS_DB_PASSWORD=analytics_pass\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_realistic_config_with_vars():
    """Create realistic config file similar to test_with_auth.yaml."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            """
app:
  name: policyengine-household-api
  environment: test
  debug: true

auth:
  enabled: true
  auth0:
    address: ${AUTH0_ADDRESS_NO_DOMAIN}
    audience: ${AUTH0_AUDIENCE_NO_DOMAIN}
    test_token: ${AUTH0_TEST_TOKEN_NO_DOMAIN}

analytics:
  enabled: true
  database:
    connection_name: ${USER_ANALYTICS_DB_CONNECTION_NAME}
    username: ${USER_ANALYTICS_DB_USERNAME}
    password: ${USER_ANALYTICS_DB_PASSWORD}
        """
        )
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def temp_no_read_permission_values_file():
    """Create a config values file with no read permissions."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write("KEY=value\n")
        temp_path = f.name

    # Remove read permissions
    os.chmod(temp_path, 0o000)

    yield temp_path

    # Restore permissions and delete
    try:
        os.chmod(temp_path, 0o644)
        Path(temp_path).unlink()
    except:
        pass  # In case file was already deleted
