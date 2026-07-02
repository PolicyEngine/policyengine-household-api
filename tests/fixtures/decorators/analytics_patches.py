"""
Patch fixtures for analytics decorator unit tests.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


@pytest.fixture
def mock_analytics_enabled():
    """Mock analytics as enabled."""
    with (
        patch(
            "policyengine_household_api.decorators.analytics.is_analytics_enabled",
            return_value=True,
        ),
        patch(
            "policyengine_household_api.decorators.analytics._collect_variable_usage",
            return_value=False,
        ),
    ):
        yield


@pytest.fixture
def mock_analytics_disabled():
    """Mock analytics as disabled."""
    with patch(
        "policyengine_household_api.decorators.analytics.is_analytics_enabled",
        return_value=False,
    ):
        yield


@pytest.fixture
def mock_analytics_error():
    """Mock analytics check to raise an error."""
    with patch(
        "policyengine_household_api.decorators.analytics.is_analytics_enabled",
        side_effect=Exception("Error"),
    ):
        yield


@pytest.fixture
def mock_request_with_auth():
    """Mock Flask request with authorization."""
    mock_request = MagicMock()
    mock_request.authorization = "Bearer valid_token"
    mock_request.endpoint = "calculate"
    mock_request.method = "POST"
    mock_request.content_length = 1024

    with patch(
        "policyengine_household_api.decorators.analytics.request",
        mock_request,
    ):
        yield mock_request


@pytest.fixture
def mock_request_without_auth():
    """Mock Flask request without authorization."""
    mock_request = MagicMock()
    mock_request.authorization = None
    mock_request.endpoint = "calculate"
    mock_request.method = "POST"
    mock_request.content_length = 1024

    with patch(
        "policyengine_household_api.decorators.analytics.request",
        mock_request,
    ):
        yield mock_request


@pytest.fixture
def mock_validated_token_sub_with_suffix():
    """Mock validated token sub to return client ID with @clients suffix."""
    with patch(
        "policyengine_household_api.decorators.analytics."
        "_sub_claim_from_validated_token",
        return_value="test-client@clients",
    ):
        yield


@pytest.fixture
def mock_validated_token_sub_without_suffix():
    """Mock validated token sub to return client ID without suffix."""
    with patch(
        "policyengine_household_api.decorators.analytics."
        "_sub_claim_from_validated_token",
        return_value="test-client",
    ):
        yield


@pytest.fixture
def mock_validated_token_sub_error():
    """Mock validated token sub extraction to raise an error."""
    with patch(
        "policyengine_household_api.decorators.analytics."
        "_sub_claim_from_validated_token",
        side_effect=Exception("Invalid token"),
    ):
        yield


@pytest.fixture
def mock_validated_token_sub_missing():
    """Mock missing validated token sub."""
    with patch(
        "policyengine_household_api.decorators.analytics."
        "_sub_claim_from_validated_token",
        return_value=None,
    ):
        yield


@pytest.fixture
def mock_datetime_fixed():
    """Mock datetime to return a fixed (UTC-aware) time."""
    from datetime import timezone

    fixed_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    with patch(
        "policyengine_household_api.decorators.analytics.datetime"
    ) as mock_dt:
        mock_dt.now.return_value = fixed_time
        # Keep the real timezone object reachable through the mock.
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        yield fixed_time


@pytest.fixture
def mock_version():
    """Mock VERSION constant."""
    with patch(
        "policyengine_household_api.decorators.analytics.VERSION",
        "1.0.0",
    ):
        yield
