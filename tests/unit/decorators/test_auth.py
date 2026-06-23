"""
Unit tests for the conditional authentication decorator.
"""

from contextlib import nullcontext
from functools import wraps
from unittest.mock import Mock
import policyengine_household_api.decorators.auth as auth_module
from policyengine_household_api.decorators.auth import (
    ANALYTICS_READ_SCOPE,
    NoOpDecorator,
    ConditionalAuthDecorator,
    ObservedAuthDecorator,
    create_auth_decorator,
    StaticBearerTokenValidator,
)
from tests.fixtures.decorators.auth import (
    AUTH0_CONFIG_DATA,
)


class _FakeResourceProtector:
    def __init__(self, error=None):
        self.error = error
        self.call_args = None
        self.acquire_token_calls = []

    def acquire_token(self, **claims):
        self.acquire_token_calls.append(claims)
        if self.error is not None:
            raise self.error
        return object()

    def __call__(self, scopes=None, optional=False, **kwargs):
        self.call_args = (scopes, optional, dict(kwargs))
        claims = dict(kwargs)
        claims["scopes"] = None if callable(scopes) else scopes

        def decorator(func):
            @wraps(func)
            def decorated(*args, **inner_kwargs):
                try:
                    self.acquire_token(**claims)
                except auth_module.MissingAuthorizationError:
                    if optional:
                        return func(*args, **inner_kwargs)
                    raise
                return func(*args, **inner_kwargs)

            return decorated

        if callable(scopes):
            return decorator(scopes)
        return decorator


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

    def test__given_test_auth_environment__uses_static_token_validator(
        self,
        auth_test_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        _, mock_protector_instance = mock_resource_protector
        mock_validator_class, _ = mock_auth0_validator

        decorator = ConditionalAuthDecorator()

        mock_validator_class.assert_not_called()
        registered_validator = (
            mock_protector_instance.register_token_validator.call_args[0][0]
        )
        assert isinstance(registered_validator, StaticBearerTokenValidator)
        assert registered_validator.expected_token == "test-jwt-token"
        assert registered_validator.scopes == ANALYTICS_READ_SCOPE
        assert decorator.get_decorator() is mock_protector_instance
        assert decorator.is_enabled is True

        auth_test_environment.assert_any_call("app.environment", "")
        auth_test_environment.assert_any_call("auth.auth0.test_token", "")
        auth_test_environment.assert_any_call(
            "auth.auth0.test_token_scopes", ""
        )

    def test__given_auth_enabled_with_valid_config__auth0_is_configured(
        self,
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

        # Verify configuration was properly read
        auth_enabled_environment.assert_any_call("auth.enabled", False)
        auth_enabled_environment.assert_any_call("auth.auth0.address", "")
        auth_enabled_environment.assert_any_call("auth.auth0.audience", "")

    def test__given_auth_enabled_missing_config__falls_back_to_noop(
        self,
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

        # Verify configuration was checked
        auth_enabled_missing_config_environment.assert_any_call(
            "auth.enabled", False
        )
        auth_enabled_missing_config_environment.assert_any_call(
            "auth.auth0.address", ""
        )
        auth_enabled_missing_config_environment.assert_any_call(
            "auth.auth0.audience", ""
        )


class TestConditionalAuthDecoratorWithAuthDisabled:
    """Test ConditionalAuthDecorator with authentication disabled."""

    def test__given_auth_disabled__returns_noop_decorator(
        self,
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

        # Verify configuration was properly read
        auth_disabled_environment.assert_any_call("auth.enabled", False)


class TestCreateAuthDecorator:
    """Test the factory function create_auth_decorator."""

    def test__given_auth_enabled__returns_observed_resource_protector(
        self,
        auth_enabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Factory wraps ResourceProtector with observability when enabled."""
        _, mock_protector_instance = mock_resource_protector

        decorator = create_auth_decorator()

        assert isinstance(decorator, ObservedAuthDecorator)
        assert decorator._decorator is mock_protector_instance

    def test__given_auth_disabled__returns_noop_decorator(
        self,
        auth_disabled_environment,
        mock_resource_protector,
        mock_auth0_validator,
    ):
        """Test that factory returns NoOpDecorator when auth is disabled."""
        decorator = create_auth_decorator()

        assert isinstance(decorator, NoOpDecorator)


class TestObservedAuthDecorator:
    def test__given_scoped_decorator__delegates_call_and_records_success(
        self,
        monkeypatch,
    ):
        attributes = []
        monkeypatch.setattr(
            auth_module,
            "segment",
            lambda _name: nullcontext(),
        )
        monkeypatch.setattr(
            auth_module,
            "set_attribute",
            lambda key, value: attributes.append((key, value)),
        )
        fake = _FakeResourceProtector()
        decorator = ObservedAuthDecorator(fake)
        view = Mock(return_value="ok")

        decorated = decorator(
            [ANALYTICS_READ_SCOPE],
            optional=True,
            custom_claim="value",
        )(view)
        result = decorated("arg", key="value")

        assert result == "ok"
        assert fake.call_args == (
            [ANALYTICS_READ_SCOPE],
            True,
            {"custom_claim": "value"},
        )
        assert fake.acquire_token_calls == [
            {
                "custom_claim": "value",
                "scopes": [ANALYTICS_READ_SCOPE],
            }
        ]
        assert attributes == [("auth_result", "success")]
        view.assert_called_once_with("arg", key="value")

    def test__given_optional_missing_auth__records_optional_missing(
        self,
        monkeypatch,
    ):
        attributes = []
        errors = []
        monkeypatch.setattr(
            auth_module,
            "segment",
            lambda _name: nullcontext(),
        )
        monkeypatch.setattr(
            auth_module,
            "set_attribute",
            lambda key, value: attributes.append((key, value)),
        )
        monkeypatch.setattr(
            auth_module,
            "record_error",
            lambda *args, **kwargs: errors.append((args, kwargs)),
        )
        fake = _FakeResourceProtector(
            error=auth_module.MissingAuthorizationError()
        )
        decorator = ObservedAuthDecorator(fake)
        view = Mock(return_value="ok")

        result = decorator(optional=True)(view)()

        assert result == "ok"
        assert attributes == [("auth_result", "optional_missing")]
        assert errors == []
        view.assert_called_once_with()


class TestStaticBearerTokenValidator:
    def test__given_static_token_without_scopes__token_has_empty_scope(self):
        validator = StaticBearerTokenValidator("test-jwt-token")

        token = validator.authenticate_token("test-jwt-token")

        assert token is not None
        assert token.get_scope() == ""

    def test__given_static_token_with_scopes__token_exposes_scopes(self):
        validator = StaticBearerTokenValidator(
            "test-jwt-token", ANALYTICS_READ_SCOPE
        )

        token = validator.authenticate_token("test-jwt-token")

        assert token is not None
        assert token.get_scope() == ANALYTICS_READ_SCOPE
