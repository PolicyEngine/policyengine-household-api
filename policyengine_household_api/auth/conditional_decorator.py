"""
Conditional authentication decorator for PolicyEngine Household API.

This module provides a flexible authentication system that can be enabled or disabled
based on configuration, allowing for easy local development without authentication
while maintaining security in production environments.
"""

from typing import Any, Callable
from authlib.integrations.flask_oauth2 import ResourceProtector
from .validation import Auth0JWTBearerTokenValidator
from ..utils.env_var_guard import create_auth0_guard


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

        Uses EnvVarGuard to determine if authentication should be enabled
        based on environment variables.
        """
        # Use Auth0 guard to check if authentication is enabled
        guard = create_auth0_guard()
        self._auth_enabled, context = guard.check()

        # Initialize the appropriate decorator
        if self._auth_enabled:
            # Extract domain and audience from context
            auth0_domain = context.get('auth0_domain')
            auth0_audience = context.get('auth0_api_audience')
            
            if auth0_domain and auth0_audience:
                # Set up real Auth0 authentication
                resource_protector = ResourceProtector()
                validator = Auth0JWTBearerTokenValidator(
                    auth0_domain, auth0_audience
                )
                resource_protector.register_token_validator(validator)
                self._decorator = resource_protector
                
                if context.get('explicitly_enabled'):
                    print("Auth0 explicitly enabled via AUTH_ENABLED")
                print(f"Auth0 authentication enabled with domain: {auth0_domain}")
            else:
                # This shouldn't happen given guard logic, but handle it
                print("Warning: Auth enabled but Auth0 configuration incomplete")
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
