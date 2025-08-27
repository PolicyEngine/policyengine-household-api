"""
Patch fixtures for analytics_setup unit tests.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def patch_get_config_value_returns_false():
    """Patch get_config_value to return False."""
    with patch(
        "policyengine_household_api.utils.get_config_value", return_value=False
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_returns_true():
    """Patch get_config_value to return True."""
    with patch(
        "policyengine_household_api.utils.get_config_value", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_raises_exception():
    """Patch get_config_value to raise an exception."""
    with patch(
        "policyengine_household_api.utils.get_config_value",
        side_effect=Exception("No config"),
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_with_full_config():
    """Patch get_config_value to return full analytics configuration."""

    def config_side_effect(key, default=None):
        config_map = {
            "analytics.enabled": True,
            "analytics.database.connection_name": "test-project:us-central1:test-instance",
            "analytics.database.username": "test_user",
            "analytics.database.password": "test_password",
        }
        return config_map.get(key, default)

    with patch(
        "policyengine_household_api.utils.get_config_value",
        side_effect=config_side_effect,
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_missing_connection_name():
    """Patch get_config_value with missing connection_name."""

    def config_side_effect(key, default=None):
        if key == "analytics.enabled":
            return True
        return default  # Returns None for connection_name

    with patch(
        "policyengine_household_api.utils.get_config_value",
        side_effect=config_side_effect,
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_missing_username():
    """Patch get_config_value with missing username."""

    def config_side_effect(key, default=None):
        if key == "analytics.enabled":
            return True
        elif key == "analytics.database.connection_name":
            return "test-project:us-central1:test-instance"
        return default  # Returns None for username

    with patch(
        "policyengine_household_api.utils.get_config_value",
        side_effect=config_side_effect,
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_missing_password():
    """Patch get_config_value with missing password."""

    def config_side_effect(key, default=None):
        config_map = {
            "analytics.enabled": True,
            "analytics.database.connection_name": "test-project:us-central1:test-instance",
            "analytics.database.username": "test_user",
        }
        return config_map.get(key, default)  # Returns None for password

    with patch(
        "policyengine_household_api.utils.get_config_value",
        side_effect=config_side_effect,
    ) as mock:
        yield mock


@pytest.fixture
def patch_get_config_value_first_call_succeeds_then_fails():
    """Patch where first call succeeds (for is_analytics_enabled) but subsequent calls fail."""
    call_count = [0]

    def config_side_effect(key, default=None):
        call_count[0] += 1
        if call_count[0] == 1:  # First call for is_analytics_enabled
            return True
        else:  # Subsequent calls fail
            raise Exception("Config loader error")

    with patch(
        "policyengine_household_api.utils.get_config_value",
        side_effect=config_side_effect,
    ) as mock:
        yield mock


@pytest.fixture
def patch_google_connector_raises_import_error():
    """Patch Google Cloud SQL Connector to raise ImportError."""
    with patch(
        "google.cloud.sql.connector.Connector",
        side_effect=ImportError("No module"),
    ) as mock:
        yield mock


@pytest.fixture
def patch_google_connector_with_connection_error():
    """Patch Google Connector where connect method fails."""
    with patch("google.cloud.sql.connector.Connector") as MockConnector:
        mock_instance = MagicMock()
        mock_instance.connect.side_effect = Exception("Connection failed")
        MockConnector.return_value = mock_instance
        yield mock_instance
