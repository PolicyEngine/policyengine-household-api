"""
Conditional authentication decorator for PolicyEngine Household API.

This module provides a flexible authentication system that can be enabled or disabled
based on configuration, allowing for easy local development without authentication
while maintaining security in production environments.
"""

from typing import Optional, Any, Callable
from authlib.integrations.flask_oauth2 import ResourceProtector
from ..auth.validation import Auth0JWTBearerTokenValidator
from ..utils.config_loader import get_config_value

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

        # Get Auth0 configuration values
        auth0_address = get_config_value("auth.auth0.address", "")
        auth0_audience = get_config_value("auth.auth0.audience", "")

        # Initialize the appropriate decorator
        if self._auth_enabled:
            if auth0_address and auth0_audience:
                # Set up real Auth0 authentication
                resource_protector = ResourceProtector()
                validator = Auth0JWTBearerTokenValidator(
                    auth0_address, auth0_audience
                )
                resource_protector.register_token_validator(validator)
                self._decorator = resource_protector
                print(
                    f"Auth0 authentication enabled with domain: {auth0_address}"
                )
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
    return conditional_auth.get_decorator()
