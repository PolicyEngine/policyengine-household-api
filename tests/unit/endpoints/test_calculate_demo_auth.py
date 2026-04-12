"""Regression tests for calculate_demo authentication."""

import importlib
from contextlib import contextmanager
from unittest.mock import patch

import policyengine_household_api.api as household_api
import policyengine_household_api.decorators.auth as auth_module


@contextmanager
def _auth_enabled_app():
    config_values = {
        "app.environment": "test_with_auth",
        "auth.enabled": True,
        "auth.auth0.address": "test-tenant.auth0.com",
        "auth.auth0.audience": "https://test-api-identifier",
        "auth.auth0.test_token": "test-jwt-token",
    }

    def get_config_value(path: str, default=None):
        return config_values.get(path, default)

    with patch(
        "policyengine_household_api.utils.config_loader.get_config_value",
        side_effect=get_config_value,
    ):
        reloaded_auth_module = importlib.reload(auth_module)
        reloaded_api_module = importlib.reload(household_api)
        try:
            yield reloaded_api_module
        finally:
            importlib.reload(reloaded_auth_module)
            importlib.reload(reloaded_api_module)


def test_calculate_demo_requires_auth_when_auth_is_enabled():
    with _auth_enabled_app() as api_module:
        client = api_module.app.test_client()

        response = client.post(
            "/us/calculate_demo",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401
