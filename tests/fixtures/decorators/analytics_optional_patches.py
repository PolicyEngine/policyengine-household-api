"""
Patch fixtures for analytics_optional decorator unit tests.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


@pytest.fixture
def mock_analytics_enabled():
    """Mock analytics as enabled."""
    with patch(
        "policyengine_household_api.data.analytics_setup.is_analytics_enabled",
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_analytics_disabled():
    """Mock analytics as disabled."""
    with patch(
        "policyengine_household_api.data.analytics_setup.is_analytics_enabled",
        return_value=False,
    ):
        yield


@pytest.fixture
def mock_analytics_error():
    """Mock analytics check to raise an error."""
    with patch(
        "policyengine_household_api.data.analytics_setup.is_analytics_enabled",
        side_effect=Exception("Error"),
    ):
        yield


@pytest.fixture
def mock_visit_instance():
    """Create a mock Visit instance."""
    return MagicMock()


@pytest.fixture
def mock_visit_class(mock_visit_instance):
    """Mock the Visit class to return a mock instance."""
    with patch(
        "policyengine_household_api.data.models.Visit",
        return_value=mock_visit_instance,
    ) as mock_class:
        yield mock_class, mock_visit_instance


@pytest.fixture
def mock_request_with_auth():
    """Mock Flask request with authorization."""
    mock_request = MagicMock()
    mock_request.authorization = "Bearer valid_token"
    mock_request.endpoint = "calculate"
    mock_request.method = "POST"
    mock_request.content_length = 1024

    with patch(
        "policyengine_household_api.decorators.analytics_optional.request",
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
        "policyengine_household_api.decorators.analytics_optional.request",
        mock_request,
    ):
        yield mock_request


@pytest.fixture
def mock_jwt_valid_with_suffix():
    """Mock JWT decode to return client ID with @clients suffix."""
    with patch("jwt.decode", return_value={"sub": "test-client@clients"}):
        yield


@pytest.fixture
def mock_jwt_valid_without_suffix():
    """Mock JWT decode to return client ID without suffix."""
    with patch("jwt.decode", return_value={"sub": "test-client"}):
        yield


@pytest.fixture
def mock_jwt_invalid():
    """Mock JWT decode to raise an error."""
    with patch("jwt.decode", side_effect=Exception("Invalid token")):
        yield


@pytest.fixture
def mock_datetime_fixed():
    """Mock datetime to return a fixed time."""
    fixed_time = datetime(2024, 1, 1, 12, 0, 0)
    with patch(
        "policyengine_household_api.decorators.analytics_optional.datetime"
    ) as mock_dt:
        mock_dt.utcnow.return_value = fixed_time
        yield fixed_time


@pytest.fixture
def mock_version():
    """Mock VERSION constant."""
    with patch(
        "policyengine_household_api.decorators.analytics_optional.VERSION",
        "1.0.0",
    ):
        yield


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch("policyengine_household_api.api.db") as mock_db:
        session = MagicMock()
        mock_db.session = session
        yield session


@pytest.fixture
def mock_db_session_with_error():
    """Mock database session where add raises an error."""
    with patch("policyengine_household_api.api.db") as mock_db:
        session = MagicMock()
        session.add.side_effect = Exception("Database error")
        mock_db.session = session
        yield session


@pytest.fixture
def setup_analytics_decorator_test(
    mock_analytics_enabled,
    mock_visit_class,
    mock_request_with_auth,
    mock_jwt_valid_with_suffix,
    mock_datetime_fixed,
    mock_version,
    mock_db_session,
):
    """Combined fixture for standard analytics decorator test setup."""
    _, visit_instance = mock_visit_class
    return {
        "visit": visit_instance,
        "session": mock_db_session,
        "fixed_time": mock_datetime_fixed,
        "request": mock_request_with_auth,
    }
