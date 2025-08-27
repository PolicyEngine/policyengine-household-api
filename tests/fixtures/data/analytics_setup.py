"""
Fixtures for analytics_setup unit tests.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import os

# Mock database connection values
MOCK_CONNECTION_NAME = "test-project:us-central1:test-instance"
MOCK_USERNAME = "test_user"
MOCK_PASSWORD = "test_password"
MOCK_DATABASE = "user_analytics"

# Analytics configuration test scenarios
ANALYTICS_DISABLED_CONFIG = {
    "analytics": {
        "enabled": False,
        "database": {"connection_name": "", "username": "", "password": ""},
    }
}

ANALYTICS_ENABLED_CONFIG = {
    "analytics": {
        "enabled": True,
        "database": {
            "connection_name": MOCK_CONNECTION_NAME,
            "username": MOCK_USERNAME,
            "password": MOCK_PASSWORD,
        },
    }
}

ANALYTICS_ENABLED_NO_CREDS_CONFIG = {
    "analytics": {
        "enabled": True,
        "database": {"connection_name": "", "username": "", "password": ""},
    }
}


@pytest.fixture
def mock_connector():
    """Mock Google Cloud SQL Connector."""
    with patch(
        "policyengine_household_api.data.analytics_setup.get_analytics_connector"
    ) as mock:
        connector_instance = MagicMock()
        connector_instance.connect = MagicMock()
        mock.return_value = connector_instance
        yield connector_instance


@pytest.fixture
def mock_google_connector():
    """Mock the actual Google Cloud SQL Connector class."""
    with patch("google.cloud.sql.connector.Connector") as MockConnector:
        instance = MagicMock()
        instance.connect = MagicMock()
        instance.close = MagicMock()
        MockConnector.return_value = instance
        yield instance


@pytest.fixture
def analytics_disabled_env(monkeypatch):
    """Environment with analytics disabled."""
    # Clear all analytics-related environment variables
    monkeypatch.delenv("ANALYTICS__ENABLED", raising=False)
    monkeypatch.delenv("USER_ANALYTICS_DB_CONNECTION_NAME", raising=False)
    monkeypatch.delenv("USER_ANALYTICS_DB_USERNAME", raising=False)
    monkeypatch.delenv("USER_ANALYTICS_DB_PASSWORD", raising=False)
    return monkeypatch


@pytest.fixture
def analytics_enabled_env(monkeypatch):
    """Environment with analytics enabled via env vars."""
    monkeypatch.setenv("ANALYTICS__ENABLED", "true")
    monkeypatch.setenv(
        "USER_ANALYTICS_DB_CONNECTION_NAME", MOCK_CONNECTION_NAME
    )
    monkeypatch.setenv("USER_ANALYTICS_DB_USERNAME", MOCK_USERNAME)
    monkeypatch.setenv("USER_ANALYTICS_DB_PASSWORD", MOCK_PASSWORD)
    return monkeypatch


@pytest.fixture
def analytics_auto_enabled_env(monkeypatch):
    """Environment where analytics is auto-enabled by presence of all credentials."""
    # Don't set ANALYTICS__ENABLED, but set all three required vars
    monkeypatch.delenv("ANALYTICS__ENABLED", raising=False)
    monkeypatch.setenv(
        "USER_ANALYTICS_DB_CONNECTION_NAME", MOCK_CONNECTION_NAME
    )
    monkeypatch.setenv("USER_ANALYTICS_DB_USERNAME", MOCK_USERNAME)
    monkeypatch.setenv("USER_ANALYTICS_DB_PASSWORD", MOCK_PASSWORD)
    return monkeypatch


@pytest.fixture
def analytics_partial_env(monkeypatch):
    """Environment with only partial analytics credentials."""
    monkeypatch.delenv("ANALYTICS__ENABLED", raising=False)
    monkeypatch.setenv(
        "USER_ANALYTICS_DB_CONNECTION_NAME", MOCK_CONNECTION_NAME
    )
    monkeypatch.setenv("USER_ANALYTICS_DB_USERNAME", MOCK_USERNAME)
    # Missing password
    monkeypatch.delenv("USER_ANALYTICS_DB_PASSWORD", raising=False)
    return monkeypatch


@pytest.fixture
def reset_analytics_state():
    """Reset global analytics state before each test."""
    # This fixture ensures tests don't affect each other
    import policyengine_household_api.data.analytics_setup as analytics

    analytics._analytics_enabled = None
    analytics._connector = None
    yield
    # Clean up after test
    analytics._analytics_enabled = None
    analytics._connector = None


@pytest.fixture
def mock_config_loader():
    """Mock the config loader to return specific configurations."""

    def _mock_config(config_dict):
        with patch(
            "policyengine_household_api.utils.get_config_value"
        ) as mock_get:

            def get_value(path, default=None):
                keys = path.split(".")
                value = config_dict
                for key in keys:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        return default
                return value

            mock_get.side_effect = get_value
            return mock_get

    return _mock_config


@pytest.fixture
def mock_pymysql_connection():
    """Mock a PyMySQL database connection."""
    connection = MagicMock()
    connection.cursor = MagicMock()
    connection.close = MagicMock()
    connection.commit = MagicMock()
    connection.rollback = MagicMock()
    return connection
