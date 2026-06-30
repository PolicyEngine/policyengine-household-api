"""
Fixtures for analytics decorator unit tests.
"""

import pytest


@pytest.fixture
def sample_function():
    """A sample function to decorate."""

    def func(arg1, arg2, kwarg1=None):
        return f"Result: {arg1}, {arg2}, {kwarg1}"

    return func


@pytest.fixture
def decorated_sample_function(sample_function):
    """Sample function with analytics decorator applied."""
    from policyengine_household_api.decorators.analytics import (
        log_analytics_if_enabled,
    )

    return log_analytics_if_enabled(sample_function)
