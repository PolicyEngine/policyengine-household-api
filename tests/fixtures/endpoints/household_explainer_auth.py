"""
Fixtures for testing Anthropic API key configuration in household_explainer endpoint.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_ai_disabled_no_key():
    """Mock configuration with AI disabled and no API key."""
    with patch("policyengine_household_api.endpoints.household_explainer.get_config_value") as mock_config:
        with patch("os.getenv") as mock_getenv:
            def config_side_effect(key, default=None):
                if key == "ai.enabled":
                    return False
                if key == "ai.anthropic.api_key":
                    return ""
                return default
            
            mock_config.side_effect = config_side_effect
            mock_getenv.return_value = None
            
            yield mock_config, mock_getenv


@pytest.fixture
def mock_ai_enabled_with_key():
    """Mock configuration with AI enabled and API key configured."""
    with patch("policyengine_household_api.endpoints.household_explainer.get_config_value") as mock_config:
        with patch("os.getenv") as mock_getenv:
            def config_side_effect(key, default=None):
                if key == "ai.enabled":
                    return True
                if key == "ai.anthropic.api_key":
                    return "sk-ant-config-key"
                return default
            
            mock_config.side_effect = config_side_effect
            mock_getenv.return_value = None
            
            yield mock_config, mock_getenv


@pytest.fixture
def mock_ai_enabled_no_key():
    """Mock configuration with AI enabled but no API key."""
    with patch("policyengine_household_api.endpoints.household_explainer.get_config_value") as mock_config:
        with patch("os.getenv") as mock_getenv:
            def config_side_effect(key, default=None):
                if key == "ai.enabled":
                    return True
                if key == "ai.anthropic.api_key":
                    return ""
                return default
            
            mock_config.side_effect = config_side_effect
            mock_getenv.return_value = None
            
            yield mock_config, mock_getenv


@pytest.fixture
def mock_backward_compatibility_env_key():
    """Mock configuration for backward compatibility with environment variable."""
    with patch("policyengine_household_api.endpoints.household_explainer.get_config_value") as mock_config:
        with patch("os.getenv") as mock_getenv:
            def config_side_effect(key, default=None):
                if key == "ai.enabled":
                    return False  # AI not explicitly enabled
                if key == "ai.anthropic.api_key":
                    return ""  # No key in config
                return default
            
            mock_config.side_effect = config_side_effect
            mock_getenv.return_value = "sk-ant-env-key"  # But key exists in env var
            
            yield mock_config, mock_getenv


@pytest.fixture
def mock_flask_app():
    """Mock Flask app for request context."""
    from flask import Flask
    return Flask(__name__)


@pytest.fixture
def mock_household_model_us():
    """Mock HouseholdModelUS for validation."""
    with patch("policyengine_household_api.endpoints.household_explainer.HouseholdModelUS") as mock_model:
        mock_model.model_validate.return_value = MagicMock()
        yield mock_model


@pytest.fixture
def mock_flatten_variables_empty():
    """Mock flatten_variables_from_household returning empty list."""
    with patch("policyengine_household_api.endpoints.household_explainer.flatten_variables_from_household") as mock_flatten:
        mock_flatten.return_value = []
        yield mock_flatten


@pytest.fixture
def mock_flatten_variables_with_data():
    """Mock flatten_variables_from_household returning a variable."""
    with patch("policyengine_household_api.endpoints.household_explainer.flatten_variables_from_household") as mock_flatten:
        mock_var = MagicMock()
        mock_var.variable = "test_var"
        mock_var.entity = "person1"
        mock_flatten.return_value = [mock_var]
        yield mock_flatten


@pytest.fixture
def mock_google_cloud_storage_not_found():
    """Mock GoogleCloudStorageManager that raises FileNotFoundError."""
    with patch("policyengine_household_api.endpoints.household_explainer.GoogleCloudStorageManager") as mock_storage:
        mock_storage_instance = MagicMock()
        mock_storage_instance.get.side_effect = FileNotFoundError("Test UUID not found")
        mock_storage.return_value = mock_storage_instance
        yield mock_storage


@pytest.fixture
def test_household_payload():
    """Standard test payload for household endpoint."""
    return {
        "computation_tree_uuid": "test-uuid",
        "household": {
            "people": {
                "person1": {"age": {"2024": 30}}
            }
        }
    }


@pytest.fixture
def test_household_payload_with_null():
    """Test payload with null variable for household endpoint."""
    return {
        "computation_tree_uuid": "test-uuid",
        "household": {
            "people": {
                "person1": {"age": {"2024": None}}
            }
        }
    }