"""
EnvVarGuard: A unified strategy for checking optional features based on environment variables.
"""
import os
import json
from typing import Any, Dict, List, Optional, Tuple, Callable
from flask import Response


class EnvVarGuard:
    """
    Guard class for checking if a feature is enabled based on environment variables.
    
    This provides a consistent pattern for handling optional features that require
    environment variables to be enabled.
    """
    
    def __init__(
        self,
        feature_name: str,
        env_vars: List[str],
        enabling_env_var: Optional[str] = None,
        side_effect: Optional[Callable[[], Any]] = None,
    ):
        """
        Initialize an EnvVarGuard.
        
        Args:
            feature_name: Human-readable name of the feature
            env_vars: List of required environment variables
            enabling_env_var: Optional environment variable that explicitly enables/disables the feature
            side_effect: Optional function to call when feature is disabled or missing required vars
                        If not provided, returns None when disabled
        """
        self.feature_name = feature_name
        self.env_vars = env_vars
        self.enabling_env_var = enabling_env_var
        self.side_effect = side_effect or (lambda: None)
        
    def check(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if the feature is enabled and return relevant context.
        
        Returns:
            Tuple of (is_enabled, context_dict) where context_dict contains
            extracted values from environment variables.
        """
        context = {}
        
        # Check if explicitly disabled via enabling_env_var
        if self.enabling_env_var:
            enabled_value = os.getenv(self.enabling_env_var, "").lower()
            if enabled_value == "false":
                return False, context
            elif enabled_value == "true":
                context['explicitly_enabled'] = True
        
        # Check required environment variables
        missing_vars = []
        for var in self.env_vars:
            value = os.getenv(var)
            if value:
                # Store in context with lowercase key
                key = var.lower()
                context[key] = value
            else:
                missing_vars.append(var)
        
        # If any required variables are missing, feature is disabled
        if missing_vars:
            context['missing_vars'] = missing_vars
            return False, context
        
        # All required variables present
        return True, context
    
    def execute_side_effect(self) -> Any:
        """
        Execute the side effect function when feature is disabled.
        
        Returns:
            The result of the side effect function
        """
        return self.side_effect()
    
    def require(self) -> Tuple[bool, Dict[str, Any], Any]:
        """
        Check if feature is enabled and execute side effect if not.
        
        Returns:
            Tuple of (is_enabled, context, side_effect_result)
            side_effect_result is None if feature is enabled
        """
        is_enabled, context = self.check()
        if not is_enabled:
            return is_enabled, context, self.execute_side_effect()
        return is_enabled, context, None


# Convenience functions for creating guards with common side effects

def create_error_response(status: int, message: str) -> Callable[[], Response]:
    """
    Create a side effect function that returns a Flask error response.
    
    Args:
        status: HTTP status code
        message: Error message
        
    Returns:
        A function that returns a Flask Response
    """
    def side_effect():
        return Response(
            json.dumps({
                "status": "error",
                "message": message,
            }),
            status=status,
            mimetype="application/json",
        )
    return side_effect


def create_silent_skip() -> Callable[[], None]:
    """
    Create a side effect function that silently skips functionality.
    
    Returns:
        A function that returns None
    """
    return lambda: None


# Pre-configured guards for common features

def create_anthropic_guard() -> EnvVarGuard:
    """Create a guard for Anthropic AI features."""
    return EnvVarGuard(
        feature_name="Anthropic AI",
        env_vars=["ANTHROPIC_API_KEY"],
        enabling_env_var="AI_ENABLED",
        side_effect=create_error_response(
            401,
            "Anthropic API key is not configured. Please contact your administrator to enable AI features."
        )
    )


def create_auth0_guard() -> EnvVarGuard:
    """Create a guard for Auth0 authentication features."""
    return EnvVarGuard(
        feature_name="Auth0 Authentication",
        env_vars=["AUTH0_DOMAIN", "AUTH0_API_AUDIENCE"],
        enabling_env_var="AUTH_ENABLED",
        side_effect=None  # Auth0 uses NoOpDecorator, not error response
    )


def create_analytics_guard() -> EnvVarGuard:
    """Create a guard for user analytics database features."""
    return EnvVarGuard(
        feature_name="User Analytics Database",
        env_vars=["USER_ANALYTICS_DB_CONNECTION_NAME", "USER_ANALYTICS_DB_USERNAME", "USER_ANALYTICS_DB_PASSWORD"],
        enabling_env_var="ANALYTICS_ENABLED",
        side_effect=create_silent_skip()
    )