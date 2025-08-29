"""
Fixtures for EnvVarGuard unit tests.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from flask import Response


# Test environment variable values
TEST_ENV_VARS = {
    "ANTHROPIC_API_KEY": "sk-ant-test-key-123",
    "AUTH0_DOMAIN": "test-domain.auth0.com",
    "AUTH0_API_AUDIENCE": "https://api.test.com",
    "USER_ANALYTICS_DB_CONNECTION_NAME": "test-project:us-central1:test-db",
    "USER_ANALYTICS_DB_USERNAME": "test_user",
    "USER_ANALYTICS_DB_PASSWORD": "test_password",
    "AI_ENABLED": "true",
    "AUTH_ENABLED": "true",
    "ANALYTICS_ENABLED": "true",
}

# Test cases for different feature configurations
ANTHROPIC_TEST_CASES = [
    {
        "description": "all vars present and enabled",
        "env_vars": {
            "ANTHROPIC_API_KEY": "sk-ant-test-key",
            "AI_ENABLED": "true",
        },
        "expected_enabled": True,
        "expected_context_keys": ["anthropic_api_key", "explicitly_enabled"],
    },
    {
        "description": "api key present but explicitly disabled",
        "env_vars": {
            "ANTHROPIC_API_KEY": "sk-ant-test-key",
            "AI_ENABLED": "false",
        },
        "expected_enabled": False,
        "expected_context_keys": [],
    },
    {
        "description": "api key missing",
        "env_vars": {
            "AI_ENABLED": "true",
        },
        "expected_enabled": False,
        "expected_context_keys": ["explicitly_enabled", "missing_vars"],
    },
    {
        "description": "no env vars set",
        "env_vars": {},
        "expected_enabled": False,
        "expected_context_keys": ["missing_vars"],
    },
]

AUTH0_TEST_CASES = [
    {
        "description": "all vars present and enabled",
        "env_vars": {
            "AUTH0_DOMAIN": "test.auth0.com",
            "AUTH0_API_AUDIENCE": "https://api.test.com",
            "AUTH_ENABLED": "true",
        },
        "expected_enabled": True,
        "expected_context_keys": ["auth0_domain", "auth0_api_audience", "explicitly_enabled"],
    },
    {
        "description": "vars present but explicitly disabled",
        "env_vars": {
            "AUTH0_DOMAIN": "test.auth0.com",
            "AUTH0_API_AUDIENCE": "https://api.test.com",
            "AUTH_ENABLED": "false",
        },
        "expected_enabled": False,
        "expected_context_keys": [],
    },
    {
        "description": "only domain present",
        "env_vars": {
            "AUTH0_DOMAIN": "test.auth0.com",
            "AUTH_ENABLED": "true",
        },
        "expected_enabled": False,
        "expected_context_keys": ["auth0_domain", "explicitly_enabled", "missing_vars"],
    },
    {
        "description": "only audience present",
        "env_vars": {
            "AUTH0_API_AUDIENCE": "https://api.test.com",
            "AUTH_ENABLED": "true",
        },
        "expected_enabled": False,
        "expected_context_keys": ["auth0_api_audience", "explicitly_enabled", "missing_vars"],
    },
]

ANALYTICS_TEST_CASES = [
    {
        "description": "all vars present and enabled",
        "env_vars": {
            "USER_ANALYTICS_DB_CONNECTION_NAME": "test:db:conn",
            "USER_ANALYTICS_DB_USERNAME": "user",
            "USER_ANALYTICS_DB_PASSWORD": "pass",
            "ANALYTICS_ENABLED": "true",
        },
        "expected_enabled": True,
        "expected_context_keys": [
            "user_analytics_db_connection_name",
            "user_analytics_db_username",
            "user_analytics_db_password",
            "explicitly_enabled",
        ],
    },
    {
        "description": "vars present but explicitly disabled",
        "env_vars": {
            "USER_ANALYTICS_DB_CONNECTION_NAME": "test:db:conn",
            "USER_ANALYTICS_DB_USERNAME": "user",
            "USER_ANALYTICS_DB_PASSWORD": "pass",
            "ANALYTICS_ENABLED": "false",
        },
        "expected_enabled": False,
        "expected_context_keys": [],
    },
    {
        "description": "missing password",
        "env_vars": {
            "USER_ANALYTICS_DB_CONNECTION_NAME": "test:db:conn",
            "USER_ANALYTICS_DB_USERNAME": "user",
            "ANALYTICS_ENABLED": "true",
        },
        "expected_enabled": False,
        "expected_context_keys": [
            "user_analytics_db_connection_name",
            "user_analytics_db_username",
            "explicitly_enabled",
            "missing_vars",
        ],
    },
]


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all test environment variables."""
    for key in TEST_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    yield monkeypatch


@pytest.fixture
def env_with_all_vars(monkeypatch):
    """Set all test environment variables."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)
    yield monkeypatch


@pytest.fixture
def env_with_anthropic(monkeypatch):
    """Set only Anthropic-related environment variables."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", TEST_ENV_VARS["ANTHROPIC_API_KEY"])
    monkeypatch.setenv("AI_ENABLED", "true")
    yield monkeypatch


@pytest.fixture
def env_with_auth0(monkeypatch):
    """Set only Auth0-related environment variables."""
    monkeypatch.setenv("AUTH0_DOMAIN", TEST_ENV_VARS["AUTH0_DOMAIN"])
    monkeypatch.setenv("AUTH0_API_AUDIENCE", TEST_ENV_VARS["AUTH0_API_AUDIENCE"])
    monkeypatch.setenv("AUTH_ENABLED", "true")
    yield monkeypatch


@pytest.fixture
def env_with_analytics(monkeypatch):
    """Set only analytics-related environment variables."""
    monkeypatch.setenv(
        "USER_ANALYTICS_DB_CONNECTION_NAME",
        TEST_ENV_VARS["USER_ANALYTICS_DB_CONNECTION_NAME"],
    )
    monkeypatch.setenv(
        "USER_ANALYTICS_DB_USERNAME", TEST_ENV_VARS["USER_ANALYTICS_DB_USERNAME"]
    )
    monkeypatch.setenv(
        "USER_ANALYTICS_DB_PASSWORD", TEST_ENV_VARS["USER_ANALYTICS_DB_PASSWORD"]
    )
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    yield monkeypatch


@pytest.fixture
def mock_response():
    """Create a mock Flask Response for testing."""

    def _create_response(status=401, message="Test error"):
        response = MagicMock(spec=Response)
        response.status_code = status
        response.get_json.return_value = {"status": "error", "message": message}
        return response

    return _create_response


@pytest.fixture
def custom_side_effect():
    """Create a custom side effect function for testing."""

    def side_effect():
        return {"custom": "result", "processed": True}

    return side_effect


@pytest.fixture
def parametrized_env(monkeypatch):
    """
    Factory fixture to set specific environment variables.
    Returns a function that takes a dict of env vars to set.
    """

    def _set_env(env_vars):
        # Clear all test env vars first
        for key in TEST_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        # Set the requested env vars
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        return monkeypatch

    return _set_env