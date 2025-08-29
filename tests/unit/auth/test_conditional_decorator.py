"""
Unit tests for the conditional authentication decorator.
"""

from unittest.mock import Mock, patch, MagicMock
import pytest
from policyengine_household_api.auth.conditional_decorator import (
    NoOpDecorator,
    ConditionalAuthDecorator,
    create_auth_decorator,
)


class TestNoOpDecorator:
    """Test the NoOpDecorator class."""

    def test__given_any_function__decorator_returns_unchanged_function(self):
        """Test that NoOpDecorator returns the function unchanged."""
        decorator = NoOpDecorator()
        original_func = Mock(return_value="test_value")

        # Apply the decorator
        decorated_func = decorator()(original_func)

        assert decorated_func is original_func
        result = decorated_func()
        assert result == "test_value"

    def test__given_decorator_with_args__args_are_ignored(self):
        """Test that NoOpDecorator ignores any arguments."""
        decorator = NoOpDecorator()
        original_func = Mock(return_value="test_value")

        # Apply decorator with various arguments (should all be ignored)
        decorated_func = decorator("arg1", kwarg1="value1")(original_func)

        assert decorated_func is original_func

    def test__given_multiple_functions__each_passes_through_unchanged(self):
        """Test that multiple functions can be decorated without interference."""
        decorator = NoOpDecorator()

        func1 = Mock(return_value="value1")
        func2 = Mock(return_value="value2")

        decorated_func1 = decorator()(func1)
        decorated_func2 = decorator()(func2)

        assert decorated_func1 is func1
        assert decorated_func2 is func2
        assert decorated_func1() == "value1"
        assert decorated_func2() == "value2"


class TestConditionalAuthDecoratorWithAuthEnabled:
    """Test ConditionalAuthDecorator with authentication enabled."""

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    @patch("policyengine_household_api.auth.conditional_decorator.ResourceProtector")
    @patch("policyengine_household_api.auth.conditional_decorator.Auth0JWTBearerTokenValidator")
    def test__given_auth_enabled_with_valid_config__auth0_is_configured(
        self,
        mock_validator_class,
        mock_protector_class,
        mock_create_guard,
        mock_print,
    ):
        """Test that Auth0 is properly configured when auth is enabled."""
        # Set up mocks
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_domain": "test.auth0.com",
                "auth0_api_audience": "https://api.test.com",
            }
        )
        mock_create_guard.return_value = mock_guard

        mock_validator_instance = MagicMock()
        mock_validator_class.return_value = mock_validator_instance

        mock_protector_instance = MagicMock()
        mock_protector_class.return_value = mock_protector_instance

        # Create decorator
        decorator = ConditionalAuthDecorator()

        # Verify Auth0 validator was created with correct parameters
        mock_validator_class.assert_called_once_with(
            "test.auth0.com", "https://api.test.com"
        )

        # Verify validator was registered with resource protector
        mock_protector_instance.register_token_validator.assert_called_once_with(
            mock_validator_instance
        )

        # Verify the decorator is the resource protector
        assert decorator.get_decorator() is mock_protector_instance
        assert decorator.is_enabled is True

        # Check console output
        mock_print.assert_any_call(
            "Auth0 authentication enabled with domain: test.auth0.com"
        )

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_auth_enabled_with_explicit_flag__shows_explicit_message(
        self,
        mock_create_guard,
        mock_print,
    ):
        """Test that explicit enabling via AUTH_ENABLED shows appropriate message."""
        # Set up mock with explicitly_enabled flag
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_domain": "test.auth0.com",
                "auth0_api_audience": "https://api.test.com",
                "explicitly_enabled": True,
            }
        )
        mock_create_guard.return_value = mock_guard

        with patch("policyengine_household_api.auth.conditional_decorator.ResourceProtector"):
            with patch("policyengine_household_api.auth.conditional_decorator.Auth0JWTBearerTokenValidator"):
                decorator = ConditionalAuthDecorator()

        # Check that explicit enable message was printed
        mock_print.assert_any_call("Auth0 explicitly enabled via AUTH_ENABLED")

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_auth_enabled_missing_domain__falls_back_to_noop(
        self,
        mock_create_guard,
        mock_print,
    ):
        """Test fallback to NoOp when auth is enabled but domain is missing."""
        # Set up mock with missing domain
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_api_audience": "https://api.test.com",
            }
        )
        mock_create_guard.return_value = mock_guard

        decorator = ConditionalAuthDecorator()

        # Verify we get a NoOpDecorator
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Check warning message
        mock_print.assert_any_call(
            "Warning: Auth enabled but Auth0 configuration incomplete"
        )


class TestConditionalAuthDecoratorWithAuthDisabled:
    """Test ConditionalAuthDecorator with authentication disabled."""

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_auth_disabled__returns_noop_decorator(
        self,
        mock_create_guard,
        mock_print,
    ):
        """Test that NoOpDecorator is used when auth is disabled."""
        # Set up mock for disabled auth
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {"missing_vars": ["AUTH0_DOMAIN"]})
        mock_create_guard.return_value = mock_guard

        decorator = ConditionalAuthDecorator()

        # Verify we get a NoOpDecorator
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Check console output
        mock_print.assert_any_call("Auth0 authentication disabled")

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_auth_explicitly_disabled__returns_noop_decorator(
        self,
        mock_create_guard,
        mock_print,
    ):
        """Test that NoOpDecorator is used when auth is explicitly disabled via AUTH_ENABLED=false."""
        # Set up mock for explicitly disabled auth
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {})
        mock_create_guard.return_value = mock_guard

        decorator = ConditionalAuthDecorator()

        # Verify we get a NoOpDecorator
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Check console output
        mock_print.assert_any_call("Auth0 authentication disabled")


class TestCreateAuthDecorator:
    """Test the factory function create_auth_decorator."""

    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    @patch("policyengine_household_api.auth.conditional_decorator.ResourceProtector")
    @patch("policyengine_household_api.auth.conditional_decorator.Auth0JWTBearerTokenValidator")
    def test__given_auth_enabled__returns_resource_protector(
        self,
        mock_validator_class,
        mock_protector_class,
        mock_create_guard,
    ):
        """Test that factory returns ResourceProtector when auth is enabled."""
        # Set up mocks
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_domain": "test.auth0.com",
                "auth0_api_audience": "https://api.test.com",
            }
        )
        mock_create_guard.return_value = mock_guard

        mock_protector_instance = MagicMock()
        mock_protector_class.return_value = mock_protector_instance

        decorator = create_auth_decorator()

        assert decorator is mock_protector_instance

    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_auth_disabled__returns_noop_decorator(
        self,
        mock_create_guard,
    ):
        """Test that factory returns NoOpDecorator when auth is disabled."""
        # Set up mock for disabled auth
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {})
        mock_create_guard.return_value = mock_guard

        decorator = create_auth_decorator()

        assert isinstance(decorator, NoOpDecorator)


class TestIntegrationWithFlaskEndpoints:
    """Test integration scenarios with Flask endpoints."""

    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    @patch("policyengine_household_api.auth.conditional_decorator.ResourceProtector")
    @patch("policyengine_household_api.auth.conditional_decorator.Auth0JWTBearerTokenValidator")
    def test__given_auth_enabled__decorator_can_be_applied_to_routes(
        self,
        mock_validator_class,
        mock_protector_class,
        mock_create_guard,
    ):
        """Test that the decorator can be applied to Flask routes."""
        # Set up mocks
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_domain": "test.auth0.com",
                "auth0_api_audience": "https://api.test.com",
            }
        )
        mock_create_guard.return_value = mock_guard

        mock_protector_instance = MagicMock()
        mock_protector_class.return_value = mock_protector_instance

        # Set up the mock to behave like a real auth decorator that modifies the response
        def mock_decorator_behavior(arg):
            def decorator(f):
                def wrapper(*args, **kwargs):
                    # Simulate auth decorator adding auth context to response
                    result = f(*args, **kwargs)
                    result["authenticated"] = True
                    result["auth_method"] = "Auth0"
                    return result

                return wrapper

            return decorator

        mock_protector_instance.side_effect = mock_decorator_behavior

        # Sample view function
        def sample_view_function():
            return {"status": "success"}

        # Get the decorator
        require_auth = create_auth_decorator()

        # Apply it like in the API
        decorated_func = require_auth(None)(sample_view_function)

        # The function should be modified by the auth decorator
        result = decorated_func()

        expected_result = {
            "status": "success",
            "authenticated": True,
            "auth_method": "Auth0",
        }

        # Verify the decorator modified the response
        assert result == expected_result

    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_auth_disabled__decorator_passes_through_routes(
        self,
        mock_create_guard,
    ):
        """Test that routes work without authentication when disabled."""
        # Set up mock for disabled auth
        mock_guard = MagicMock()
        mock_guard.check.return_value = (False, {})
        mock_create_guard.return_value = mock_guard

        # Sample view function
        def sample_view_function():
            return {"status": "success"}

        require_auth = create_auth_decorator()

        # Apply the no-op decorator
        decorated_func = require_auth(None)(sample_view_function)

        # Function should be unchanged (no wrapper)
        assert decorated_func is sample_view_function

        # Call the function
        result = decorated_func()

        # Verify response is unmodified (no auth context added)
        assert result == {"status": "success"}
        assert "authenticated" not in result
        assert "auth_method" not in result


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    @patch("policyengine_household_api.auth.conditional_decorator.ResourceProtector")
    @patch("policyengine_household_api.auth.conditional_decorator.Auth0JWTBearerTokenValidator")
    def test__given_get_decorator_called_multiple_times__returns_same_instance(
        self,
        mock_validator_class,
        mock_protector_class,
        mock_create_guard,
    ):
        """Test that get_decorator always returns the same instance."""
        # Set up mocks
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_domain": "test.auth0.com",
                "auth0_api_audience": "https://api.test.com",
            }
        )
        mock_create_guard.return_value = mock_guard

        mock_protector_instance = MagicMock()
        mock_protector_class.return_value = mock_protector_instance

        decorator = ConditionalAuthDecorator()

        decorator1 = decorator.get_decorator()
        decorator2 = decorator.get_decorator()

        assert decorator1 is decorator2

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    @patch("policyengine_household_api.auth.conditional_decorator.create_auth0_guard")
    def test__given_incomplete_auth0_config__warning_is_shown(
        self,
        mock_create_guard,
        mock_print,
    ):
        """Test that incomplete Auth0 config shows appropriate warning."""
        # Set up mock with incomplete config (audience but no domain)
        mock_guard = MagicMock()
        mock_guard.check.return_value = (
            True,
            {
                "auth0_api_audience": "https://api.test.com",
                # auth0_domain is missing
            }
        )
        mock_create_guard.return_value = mock_guard

        decorator = ConditionalAuthDecorator()

        # Should fall back to NoOp
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Check warning message
        mock_print.assert_any_call(
            "Warning: Auth enabled but Auth0 configuration incomplete"
        )