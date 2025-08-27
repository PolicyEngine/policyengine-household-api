"""
Unit tests for the conditional authentication decorator.
"""

from unittest.mock import Mock, patch
from policyengine_household_api.auth.conditional_decorator import (
    NoOpDecorator,
    ConditionalAuthDecorator,
    create_auth_decorator,
)
from tests.fixtures.auth.conditional_decorator import (
    AUTH0_CONFIG_DATA,
    auth_enabled_environment,
    auth_disabled_environment,
    auth_enabled_missing_config_environment,
    auth_backward_compat_environment,
    auth_partial_config_environment,
    mock_resource_protector,
    mock_auth0_validator,
    mock_flask_app,
    sample_view_function,
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
    def test__given_auth_enabled_with_valid_config__auth0_is_configured(
        self,
        mock_print,
        auth_enabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that Auth0 is properly configured when auth is enabled."""
        mock_protector_class, mock_protector_instance = mock_resource_protector
        mock_validator_class, mock_validator_instance = mock_auth0_validator

        decorator = ConditionalAuthDecorator()

        # Verify Auth0 validator was created with correct parameters
        mock_validator_class.assert_called_once_with(
            AUTH0_CONFIG_DATA["address"], AUTH0_CONFIG_DATA["audience"]
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
            f"Auth0 authentication enabled with domain: {AUTH0_CONFIG_DATA['address']}"
        )

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    def test__given_auth_enabled_missing_config__falls_back_to_noop(
        self,
        mock_print,
        auth_enabled_missing_config_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test fallback to NoOp when auth is enabled but config is missing."""
        mock_protector_class, _ = mock_resource_protector
        mock_validator_class, _ = mock_auth0_validator

        decorator = ConditionalAuthDecorator()

        # Verify Auth0 components were not created
        mock_validator_class.assert_not_called()
        mock_protector_class.assert_not_called()

        # Verify we get a NoOpDecorator
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Check warning message
        mock_print.assert_any_call(
            "Warning: Auth enabled but Auth0 configuration missing"
        )


class TestConditionalAuthDecoratorWithAuthDisabled:
    """Test ConditionalAuthDecorator with authentication disabled."""

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    def test__given_auth_disabled__returns_noop_decorator(
        self,
        mock_print,
        auth_disabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that NoOpDecorator is used when auth is disabled."""
        mock_protector_class, _ = mock_resource_protector
        mock_validator_class, _ = mock_auth0_validator

        decorator = ConditionalAuthDecorator()

        # Verify Auth0 components were not created
        mock_validator_class.assert_not_called()
        mock_protector_class.assert_not_called()

        # Verify we get a NoOpDecorator
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Check console output
        mock_print.assert_any_call("Auth0 authentication disabled")


class TestConditionalAuthDecoratorBackwardCompatibility:
    """Test backward compatibility scenarios."""

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    def test__given_auth0_config_present__auto_enables_auth(
        self,
        mock_print,
        auth_backward_compat_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test auto-enabling auth when Auth0 config is present."""
        mock_protector_class, mock_protector_instance = mock_resource_protector
        mock_validator_class, mock_validator_instance = mock_auth0_validator

        decorator = ConditionalAuthDecorator()

        # Verify Auth0 was configured despite auth.enabled being False
        mock_validator_class.assert_called_once_with(
            AUTH0_CONFIG_DATA["address"], AUTH0_CONFIG_DATA["audience"]
        )
        mock_protector_instance.register_token_validator.assert_called_once()

        assert decorator.get_decorator() is mock_protector_instance
        assert decorator.is_enabled is True

        # Check auto-enable message
        mock_print.assert_any_call(
            "Auth0 auto-enabled due to presence of AUTH0 configuration"
        )

    @patch("policyengine_household_api.auth.conditional_decorator.print")
    def test__given_partial_auth0_config__remains_disabled(
        self,
        mock_print,
        auth_partial_config_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that partial Auth0 config doesn't auto-enable auth."""
        mock_protector_class, _ = mock_resource_protector
        mock_validator_class, _ = mock_auth0_validator

        decorator = ConditionalAuthDecorator()

        # Verify Auth0 components were not created
        mock_validator_class.assert_not_called()
        mock_protector_class.assert_not_called()

        # Should remain disabled with partial config
        assert isinstance(decorator.get_decorator(), NoOpDecorator)
        assert decorator.is_enabled is False

        # Should not show auto-enable message - check all print calls
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert not any("auto-enabled" in call for call in print_calls)
        mock_print.assert_any_call("Auth0 authentication disabled")


class TestCreateAuthDecorator:
    """Test the factory function create_auth_decorator."""

    def test__given_auth_enabled__returns_resource_protector(
        self,
        auth_enabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that factory returns ResourceProtector when auth is enabled."""
        _, mock_protector_instance = mock_resource_protector

        decorator = create_auth_decorator()

        assert decorator is mock_protector_instance

    def test__given_auth_disabled__returns_noop_decorator(
        self,
        auth_disabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that factory returns NoOpDecorator when auth is disabled."""
        decorator = create_auth_decorator()

        assert isinstance(decorator, NoOpDecorator)

    def test__given_backward_compat__returns_resource_protector(
        self,
        auth_backward_compat_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test factory behavior with backward compatibility."""
        _, mock_protector_instance = mock_resource_protector

        decorator = create_auth_decorator()

        assert decorator is mock_protector_instance


class TestIntegrationWithFlaskEndpoints:
    """Test integration scenarios with Flask endpoints."""

    def test__given_auth_enabled__decorator_can_be_applied_to_routes(
        self,
        auth_enabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
        sample_view_function,
    ):
        """Test that the decorator can be applied to Flask routes."""
        _, mock_protector_instance = mock_resource_protector

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

    def test__given_auth_disabled__decorator_passes_through_routes(
        self, auth_disabled_environment, sample_view_function
    ):
        """Test that routes work without authentication when disabled."""
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

    def test__given_get_decorator_called_multiple_times__returns_same_instance(
        self,
        auth_enabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that get_decorator always returns the same instance."""
        decorator = ConditionalAuthDecorator()

        decorator1 = decorator.get_decorator()
        decorator2 = decorator.get_decorator()

        assert decorator1 is decorator2
