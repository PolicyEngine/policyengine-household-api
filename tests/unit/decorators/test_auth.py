"""
Unit tests for the conditional authentication decorator.
"""

from unittest.mock import Mock, patch
from policyengine_household_api.decorators.auth import (
    NoOpDecorator,
    ConditionalAuthDecorator,
    create_auth_decorator,
)
from tests.fixtures.decorators.auth import (
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

    @patch("policyengine_household_api.decorators.auth.print")
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

    @patch("policyengine_household_api.decorators.auth.print")
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

    @patch("policyengine_household_api.decorators.auth.print")
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
