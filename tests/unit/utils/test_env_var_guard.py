"""
Unit tests for the EnvVarGuard class.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch
from flask import Response

from policyengine_household_api.utils.env_var_guard import (
    EnvVarGuard,
    create_error_response,
    create_silent_skip,
    create_anthropic_guard,
    create_auth0_guard,
    create_analytics_guard,
)


class TestEnvVarGuardInitialization:
    """Test EnvVarGuard initialization and basic setup."""

    def test__given_minimal_arguments__guard_initializes_with_defaults(self):
        """Test that EnvVarGuard initializes with minimal required arguments."""
        guard = EnvVarGuard(
            feature_name="Test Feature",
            env_vars=["TEST_VAR"],
        )

        assert guard.feature_name == "Test Feature"
        assert guard.env_vars == ["TEST_VAR"]
        assert guard.enabling_env_var is None
        assert guard.side_effect is not None

    def test__given_all_arguments__guard_stores_all_values(self):
        """Test initialization with all optional arguments provided."""
        side_effect = lambda: "custom_result"
        guard = EnvVarGuard(
            feature_name="Full Feature",
            env_vars=["VAR1", "VAR2"],
            enabling_env_var="FEATURE_ENABLED",
            side_effect=side_effect,
        )

        assert guard.feature_name == "Full Feature"
        assert guard.env_vars == ["VAR1", "VAR2"]
        assert guard.enabling_env_var == "FEATURE_ENABLED"
        assert guard.side_effect == side_effect


class TestEnvVarCheck:
    """Test the check() method for various environment configurations."""

    def test__given_all_required_vars_present__check_returns_enabled(self, monkeypatch):
        """Test that check returns enabled when all required vars are present."""
        monkeypatch.setenv("API_KEY", "test_key")
        monkeypatch.setenv("API_URL", "https://example.com")

        guard = EnvVarGuard(
            feature_name="API Feature",
            env_vars=["API_KEY", "API_URL"],
        )

        is_enabled, context = guard.check()

        assert is_enabled is True
        assert context["api_key"] == "test_key"
        assert context["api_url"] == "https://example.com"

    def test__given_missing_required_vars__check_returns_disabled(self, monkeypatch):
        """Test that check returns disabled when required vars are missing."""
        monkeypatch.setenv("API_KEY", "test_key")
        # API_URL is missing

        guard = EnvVarGuard(
            feature_name="API Feature",
            env_vars=["API_KEY", "API_URL"],
        )

        is_enabled, context = guard.check()

        assert is_enabled is False
        assert context["api_key"] == "test_key"
        assert "missing_vars" in context
        assert "API_URL" in context["missing_vars"]

    def test__given_empty_string_var__check_treats_as_missing(self, monkeypatch):
        """Test that empty string environment variables are treated as missing."""
        monkeypatch.setenv("API_KEY", "")
        monkeypatch.setenv("API_URL", "https://example.com")

        guard = EnvVarGuard(
            feature_name="API Feature",
            env_vars=["API_KEY", "API_URL"],
        )

        is_enabled, context = guard.check()

        assert is_enabled is False
        assert "missing_vars" in context
        assert "API_KEY" in context["missing_vars"]


class TestEnablingEnvVar:
    """Test the enabling environment variable functionality."""

    def test__given_enabling_var_false__check_returns_disabled_regardless_of_required_vars(
        self, monkeypatch
    ):
        """Test that enabling_env_var=false disables feature even with all required vars."""
        monkeypatch.setenv("API_KEY", "test_key")
        monkeypatch.setenv("FEATURE_ENABLED", "false")

        guard = EnvVarGuard(
            feature_name="Optional Feature",
            env_vars=["API_KEY"],
            enabling_env_var="FEATURE_ENABLED",
        )

        is_enabled, context = guard.check()

        assert is_enabled is False
        assert "api_key" not in context  # Not checked when explicitly disabled

    def test__given_enabling_var_true__check_still_requires_all_vars(self, monkeypatch):
        """Test that enabling_env_var=true still requires all vars to be present."""
        monkeypatch.setenv("FEATURE_ENABLED", "true")
        # API_KEY is missing

        guard = EnvVarGuard(
            feature_name="Optional Feature",
            env_vars=["API_KEY"],
            enabling_env_var="FEATURE_ENABLED",
        )

        is_enabled, context = guard.check()

        assert is_enabled is False
        assert context["explicitly_enabled"] is True
        assert "missing_vars" in context
        assert "API_KEY" in context["missing_vars"]

    def test__given_enabling_var_true_and_all_vars__check_returns_enabled(
        self, monkeypatch
    ):
        """Test that enabling_env_var=true with all vars returns enabled."""
        monkeypatch.setenv("API_KEY", "test_key")
        monkeypatch.setenv("FEATURE_ENABLED", "TRUE")  # Test case insensitivity

        guard = EnvVarGuard(
            feature_name="Optional Feature",
            env_vars=["API_KEY"],
            enabling_env_var="FEATURE_ENABLED",
        )

        is_enabled, context = guard.check()

        assert is_enabled is True
        assert context["explicitly_enabled"] is True
        assert context["api_key"] == "test_key"

    def test__given_enabling_var_not_set__check_proceeds_with_normal_logic(
        self, monkeypatch
    ):
        """Test that missing enabling_env_var doesn't affect normal checking."""
        monkeypatch.setenv("API_KEY", "test_key")
        # FEATURE_ENABLED is not set

        guard = EnvVarGuard(
            feature_name="Optional Feature",
            env_vars=["API_KEY"],
            enabling_env_var="FEATURE_ENABLED",
        )

        is_enabled, context = guard.check()

        assert is_enabled is True
        assert "explicitly_enabled" not in context
        assert context["api_key"] == "test_key"


class TestSideEffects:
    """Test side effect execution functionality."""

    def test__given_custom_side_effect__execute_returns_result(self):
        """Test that execute_side_effect returns the side effect result."""
        side_effect_result = {"error": "Feature disabled"}
        guard = EnvVarGuard(
            feature_name="Test Feature",
            env_vars=["TEST_VAR"],
            side_effect=lambda: side_effect_result,
        )

        result = guard.execute_side_effect()

        assert result == side_effect_result

    def test__given_no_side_effect__execute_returns_none(self):
        """Test that default side effect returns None."""
        guard = EnvVarGuard(
            feature_name="Test Feature",
            env_vars=["TEST_VAR"],
        )

        result = guard.execute_side_effect()

        assert result is None


class TestRequireMethod:
    """Test the require() method that combines check and side effects."""

    def test__given_feature_enabled__require_returns_no_side_effect(self, monkeypatch):
        """Test that require returns None for side_effect when feature is enabled."""
        monkeypatch.setenv("API_KEY", "test_key")

        guard = EnvVarGuard(
            feature_name="Test Feature",
            env_vars=["API_KEY"],
            side_effect=lambda: "side_effect_result",
        )

        is_enabled, context, side_effect_result = guard.require()

        assert is_enabled is True
        assert context["api_key"] == "test_key"
        assert side_effect_result is None

    def test__given_feature_disabled__require_executes_side_effect(self, monkeypatch):
        """Test that require executes side effect when feature is disabled."""
        # API_KEY is not set
        side_effect_value = "disabled_result"
        guard = EnvVarGuard(
            feature_name="Test Feature",
            env_vars=["API_KEY"],
            side_effect=lambda: side_effect_value,
        )

        is_enabled, context, side_effect_result = guard.require()

        assert is_enabled is False
        assert "missing_vars" in context
        assert side_effect_result == side_effect_value


class TestConvenienceFunctions:
    """Test convenience functions for creating side effects."""

    def test__given_error_response_params__create_error_response_returns_flask_response(
        self,
    ):
        """Test that create_error_response creates a proper Flask Response."""
        side_effect = create_error_response(403, "Access denied")
        result = side_effect()

        assert isinstance(result, Response)
        assert result.status_code == 403
        assert result.mimetype == "application/json"

        data = json.loads(result.get_data(as_text=True))
        assert data["status"] == "error"
        assert data["message"] == "Access denied"

    def test__given_silent_skip__function_returns_none(self):
        """Test that create_silent_skip returns a function that returns None."""
        side_effect = create_silent_skip()
        result = side_effect()

        assert result is None


class TestPreConfiguredGuards:
    """Test pre-configured guard factory functions."""

    def test__given_anthropic_guard__configuration_is_correct(self):
        """Test that create_anthropic_guard has correct configuration."""
        guard = create_anthropic_guard()

        assert guard.feature_name == "Anthropic AI"
        assert guard.env_vars == ["ANTHROPIC_API_KEY"]
        assert guard.enabling_env_var == "AI_ENABLED"
        assert guard.side_effect is not None

        # Test side effect returns error response
        result = guard.execute_side_effect()
        assert isinstance(result, Response)
        assert result.status_code == 401

    def test__given_auth0_guard__configuration_is_correct(self):
        """Test that create_auth0_guard has correct configuration."""
        guard = create_auth0_guard()

        assert guard.feature_name == "Auth0 Authentication"
        assert guard.env_vars == ["AUTH0_DOMAIN", "AUTH0_API_AUDIENCE"]
        assert guard.enabling_env_var == "AUTH_ENABLED"
        # Auth0 uses None side effect (NoOpDecorator handles it)
        assert guard.execute_side_effect() is None

    def test__given_analytics_guard__configuration_is_correct(self):
        """Test that create_analytics_guard has correct configuration."""
        guard = create_analytics_guard()

        assert guard.feature_name == "User Analytics Database"
        assert guard.env_vars == [
            "USER_ANALYTICS_DB_CONNECTION_NAME",
            "USER_ANALYTICS_DB_USERNAME",
            "USER_ANALYTICS_DB_PASSWORD",
        ]
        assert guard.enabling_env_var == "ANALYTICS_ENABLED"
        # Analytics uses silent skip
        assert guard.execute_side_effect() is None


class TestMultipleEnvVars:
    """Test behavior with multiple environment variables."""

    def test__given_multiple_vars_all_present__context_contains_all(self, monkeypatch):
        """Test that all environment variables are captured in context."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "testdb")

        guard = EnvVarGuard(
            feature_name="Database",
            env_vars=["DB_HOST", "DB_PORT", "DB_NAME"],
        )

        is_enabled, context = guard.check()

        assert is_enabled is True
        assert context["db_host"] == "localhost"
        assert context["db_port"] == "5432"
        assert context["db_name"] == "testdb"

    def test__given_multiple_vars_some_missing__context_shows_missing(
        self, monkeypatch
    ):
        """Test that missing vars are properly tracked with multiple vars."""
        monkeypatch.setenv("DB_HOST", "localhost")
        # DB_PORT and DB_NAME are missing

        guard = EnvVarGuard(
            feature_name="Database",
            env_vars=["DB_HOST", "DB_PORT", "DB_NAME"],
        )

        is_enabled, context = guard.check()

        assert is_enabled is False
        assert context["db_host"] == "localhost"
        assert "missing_vars" in context
        assert set(context["missing_vars"]) == {"DB_PORT", "DB_NAME"}


class TestCaseInsensitivity:
    """Test case insensitivity for enabling environment variable."""

    def test__given_various_false_values__all_disable_feature(self, monkeypatch):
        """Test that various representations of false disable the feature."""
        test_cases = ["false", "False", "FALSE", "FaLsE"]

        for value in test_cases:
            monkeypatch.setenv("FEATURE_ENABLED", value)
            monkeypatch.setenv("API_KEY", "test_key")

            guard = EnvVarGuard(
                feature_name="Test Feature",
                env_vars=["API_KEY"],
                enabling_env_var="FEATURE_ENABLED",
            )

            is_enabled, _ = guard.check()
            assert is_enabled is False, f"Failed for value: {value}"

    def test__given_various_true_values__all_enable_feature_check(self, monkeypatch):
        """Test that various representations of true enable feature checking."""
        test_cases = ["true", "True", "TRUE", "TrUe"]

        for value in test_cases:
            monkeypatch.setenv("FEATURE_ENABLED", value)
            monkeypatch.setenv("API_KEY", "test_key")

            guard = EnvVarGuard(
                feature_name="Test Feature",
                env_vars=["API_KEY"],
                enabling_env_var="FEATURE_ENABLED",
            )

            is_enabled, context = guard.check()
            assert is_enabled is True, f"Failed for value: {value}"
            assert context["explicitly_enabled"] is True