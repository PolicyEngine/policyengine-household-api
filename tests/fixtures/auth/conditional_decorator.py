"""
Fixtures for conditional decorator unit tests.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any


# Sample Auth0 configuration data
AUTH0_CONFIG_DATA = {
    "address": "test-tenant.auth0.com",
    "audience": "https://test-api-identifier",
}

# Configuration scenarios for testing
AUTH_ENABLED_CONFIG = {
    "auth": {
        "enabled": True,
        "auth0": AUTH0_CONFIG_DATA,
    }
}

AUTH_DISABLED_CONFIG = {
    "auth": {
        "enabled": False,
        "auth0": {
            "address": "",
            "audience": "",
        },
    }
}

AUTH_ENABLED_MISSING_CONFIG = {
    "auth": {
        "enabled": True,
        "auth0": {
            "address": "",
            "audience": "",
        },
    }
}

AUTH_BACKWARD_COMPAT_CONFIG = {
    "auth": {
        "enabled": False,  # Explicitly disabled
        "auth0": AUTH0_CONFIG_DATA,  # But Auth0 config present
    }
}

AUTH_PARTIAL_CONFIG = {
    "auth": {
        "enabled": False,
        "auth0": {
            "address": "test-tenant.auth0.com",  # Only address present
            "audience": "",
        },
    }
}


@pytest.fixture
def mock_resource_protector():
    """Mock the ResourceProtector class."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.ResourceProtector"
    ) as mock_class:
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        yield mock_class, mock_instance


@pytest.fixture
def mock_auth0_validator():
    """Mock the Auth0JWTBearerTokenValidator class."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.Auth0JWTBearerTokenValidator"
    ) as mock_class:
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        yield mock_class, mock_instance


@pytest.fixture
def auth_enabled_environment():
    """Set up environment with authentication enabled."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.get_config_value"
    ) as mock_config:

        def config_side_effect(path: str, default: Any = None) -> Any:
            config_map = {
                "auth.enabled": True,
                "auth.auth0.address": AUTH0_CONFIG_DATA["address"],
                "auth.auth0.audience": AUTH0_CONFIG_DATA["audience"],
            }
            return config_map.get(path, default)

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def auth_disabled_environment():
    """Set up environment with authentication disabled."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.get_config_value"
    ) as mock_config:

        def config_side_effect(path: str, default: Any = None) -> Any:
            config_map = {
                "auth.enabled": False,
                "auth.auth0.address": "",
                "auth.auth0.audience": "",
            }
            return config_map.get(path, default)

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def auth_enabled_missing_config_environment():
    """Set up environment with auth enabled but missing Auth0 config."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.get_config_value"
    ) as mock_config:

        def config_side_effect(path: str, default: Any = None) -> Any:
            config_map = {
                "auth.enabled": True,
                "auth.auth0.address": "",
                "auth.auth0.audience": "",
            }
            return config_map.get(path, default)

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def auth_backward_compat_environment():
    """Set up environment for backward compatibility testing."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.get_config_value"
    ) as mock_config:

        def config_side_effect(path: str, default: Any = None) -> Any:
            config_map = {
                "auth.enabled": False,  # Not explicitly enabled
                "auth.auth0.address": AUTH0_CONFIG_DATA["address"],
                "auth.auth0.audience": AUTH0_CONFIG_DATA["audience"],
            }
            return config_map.get(path, default)

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def auth_partial_config_environment():
    """Set up environment with partial Auth0 configuration."""
    with patch(
        "policyengine_household_api.auth.conditional_decorator.get_config_value"
    ) as mock_config:

        def config_side_effect(path: str, default: Any = None) -> Any:
            config_map = {
                "auth.enabled": False,
                "auth.auth0.address": AUTH0_CONFIG_DATA["address"],
                "auth.auth0.audience": "",  # Missing audience
            }
            return config_map.get(path, default)

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def mock_flask_app():
    """Create a mock Flask application for testing decorators."""
    app = Mock()
    app.route = Mock()
    return app


@pytest.fixture
def sample_view_function():
    """Create a sample view function for testing decorators."""

    def view_func():
        return {"status": "success"}

    return view_func
