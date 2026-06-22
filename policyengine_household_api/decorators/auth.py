"""
Conditional authentication decorator for PolicyEngine Household API.

This module provides a flexible authentication system that can be enabled or disabled
based on configuration, allowing for easy local development without authentication
while maintaining security in production environments.
"""

from functools import wraps
from typing import Optional, Any, Callable
from authlib.integrations.flask_oauth2.resource_protector import (
    MissingAuthorizationError,
    OAuth2Error,
)
from authlib.integrations.flask_oauth2 import ResourceProtector
from authlib.oauth2.rfc6750 import BearerTokenValidator
from policyengine_observability import record_error
from policyengine_observability import segment
from policyengine_observability import set_attribute

from ..auth.validation import Auth0JWTBearerTokenValidator
from ..observability.segments import SegmentName
from ..utils.config_loader import get_config_value

ANALYTICS_READ_SCOPE = "read:calculate-analytics"


class StaticBearerToken:
    """Minimal token object for test-only bearer token validation."""

    def __init__(self, token_string: str, scope: str = ""):
        self.token_string = token_string
        self.scope = scope

    def is_expired(self) -> bool:
        return False

    def is_revoked(self) -> bool:
        return False

    def get_scope(self) -> str:
        return self.scope


class StaticBearerTokenValidator(BearerTokenValidator):
    """Accept a single configured bearer token for test environments."""

    def __init__(self, expected_token: str, scopes: str | None = ""):
        super().__init__()
        self.expected_token = expected_token
        self.scopes = scopes or ""

    def authenticate_token(
        self, token_string: Optional[str]
    ) -> Optional[StaticBearerToken]:
        if token_string == self.expected_token:
            return StaticBearerToken(token_string, scope=self.scopes)
        return None


class NoOpDecorator:
    """
    No-operation decorator used when authentication is disabled.

    This class mimics the interface of ResourceProtector but doesn't
    perform any authentication checks, allowing requests to pass through.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Callable:
        """
        Return a pass-through decorator.

        Args:
            *args: Unused positional arguments for compatibility
            **kwargs: Unused keyword arguments for compatibility

        Returns:
            A decorator function that returns the original function unchanged
        """

        def decorator(f: Callable) -> Callable:
            return f

        return decorator


class ConditionalAuthDecorator:
    """
    Manages conditional authentication based on configuration.

    This class determines whether authentication should be enabled based on
    configuration values and environment variables, then provides the appropriate
    decorator (either a real authentication decorator or a no-op).
    """

    def __init__(self):
        """Initialize the conditional auth decorator."""
        self._auth_enabled = False
        self._decorator = None
        self._setup_authentication()

    def _setup_authentication(self) -> None:
        """
        Set up authentication based on configuration.

        Authentication is enabled if:
        1. The auth.enabled config value is True, OR
        2. Both Auth0 configuration values are present (backward compatibility)
        """
        # Check if Auth0 is explicitly enabled via configuration
        self._auth_enabled = get_config_value("auth.enabled", False)
        app_environment = get_config_value("app.environment", "")
        auth0_test_token = get_config_value("auth.auth0.test_token", "")
        auth0_test_token_scopes = get_config_value(
            "auth.auth0.test_token_scopes", ""
        )

        # Get Auth0 configuration values
        auth0_address = get_config_value("auth.auth0.address", "")
        auth0_audience = get_config_value("auth.auth0.audience", "")

        # Initialize the appropriate decorator
        if self._auth_enabled:
            if app_environment == "test_with_auth" and auth0_test_token:
                resource_protector = ResourceProtector()
                resource_protector.register_token_validator(
                    StaticBearerTokenValidator(
                        auth0_test_token, auth0_test_token_scopes
                    )
                )
                self._decorator = resource_protector
            elif auth0_address and auth0_audience:
                # Set up real Auth0 authentication
                resource_protector = ResourceProtector()
                validator = Auth0JWTBearerTokenValidator(
                    auth0_address, auth0_audience
                )
                resource_protector.register_token_validator(validator)
                self._decorator = resource_protector
            else:
                # Auth was requested but configuration is missing
                print("Warning: Auth enabled but Auth0 configuration missing")
                self._auth_enabled = False
                self._decorator = NoOpDecorator()
        else:
            # Authentication is disabled
            self._decorator = NoOpDecorator()
            print("Auth0 authentication disabled")

    def get_decorator(self) -> Any:
        """
        Get the appropriate decorator based on configuration.

        Returns:
            Either a ResourceProtector for real authentication or a NoOpDecorator
        """
        return self._decorator

    @property
    def is_enabled(self) -> bool:
        """
        Check if authentication is enabled.

        Returns:
            True if authentication is enabled, False otherwise
        """
        return self._auth_enabled


def create_auth_decorator() -> Any:
    """
    Factory function to create the appropriate authentication decorator.

    This is the main entry point for the API to get an authentication decorator
    that will either enforce Auth0 JWT validation or pass through requests
    based on configuration.

    Returns:
        An authentication decorator (ResourceProtector or NoOpDecorator)
    """
    conditional_auth = ConditionalAuthDecorator()
    decorator = conditional_auth.get_decorator()
    if not conditional_auth.is_enabled:
        return decorator
    return ObservedAuthDecorator(decorator)


class ObservedAuthDecorator:
    """Wrap an auth decorator with coarse request-path observability."""

    def __init__(self, decorator: Any):
        self._decorator = decorator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._decorator, name)

    def __call__(self, *args: Any, **kwargs: Any) -> Callable:
        if args and callable(args[0]):
            return self._decorate(args[0], scopes=None, optional=False)
        scopes = args[0] if args else kwargs.pop("scopes", None)
        optional = bool(kwargs.pop("optional", False))
        claims = dict(kwargs)
        claims["scopes"] = scopes
        for claim in claims:
            if isinstance(claims[claim], str):
                claims[claim] = [claims[claim]]

        def decorator(func: Callable) -> Callable:
            return self._decorate(
                func,
                optional=optional,
                **claims,
            )

        return decorator

    def _decorate(
        self,
        func: Callable,
        *,
        optional: bool,
        **claims: Any,
    ) -> Callable:
        @wraps(func)
        def wrapper(*func_args: Any, **func_kwargs: Any) -> Any:
            optional_missing = False
            with segment(SegmentName.AUTH):
                try:
                    self._decorator.acquire_token(**claims)
                except MissingAuthorizationError as exc:
                    if optional:
                        set_attribute("auth_result", "optional_missing")
                        optional_missing = True
                    else:
                        self._record_auth_error(exc)
                        self._decorator.raise_error_response(exc)
                except OAuth2Error as exc:
                    self._record_auth_error(exc)
                    self._decorator.raise_error_response(exc)
            if optional_missing:
                return func(*func_args, **func_kwargs)
            set_attribute("auth_result", "success")
            return func(*func_args, **func_kwargs)

        return wrapper

    def _record_auth_error(self, exc: Exception) -> None:
        set_attribute("auth_result", "failed")
        status_code = getattr(
            exc,
            "status_code",
            getattr(exc, "code", 401),
        )
        record_error(
            exc,
            handled=True,
            status_code=status_code,
            include_stack=False,
        )
