"""
Fixtures for analytics decorator unit tests.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
import jwt


# Mock request data
MOCK_JWT_TOKEN = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LWNsaWVudEBjbGllbnRzIiwiZXhwIjoxNjQwOTk1MjAwfQ.test"
MOCK_CLIENT_ID = "test-client"
MOCK_CLIENT_ID_WITH_SUFFIX = "test-client@clients"
MOCK_ENDPOINT = "calculate"
MOCK_METHOD = "POST"
MOCK_CONTENT_LENGTH = 1024
MOCK_API_VERSION = "1.0.0"


@pytest.fixture
def mock_flask_request():
    """Mock Flask request object."""
    request = MagicMock()
    request.authorization = MOCK_JWT_TOKEN
    request.endpoint = MOCK_ENDPOINT
    request.method = MOCK_METHOD
    request.content_length = MOCK_CONTENT_LENGTH
    return request


@pytest.fixture
def mock_flask_request_no_auth():
    """Mock Flask request object without authorization."""
    request = MagicMock()
    request.authorization = None
    request.endpoint = MOCK_ENDPOINT
    request.method = MOCK_METHOD
    request.content_length = MOCK_CONTENT_LENGTH
    return request


@pytest.fixture
def mock_jwt_decode():
    """Mock JWT decode to return a test client ID."""
    with patch("jwt.decode") as mock_decode:
        mock_decode.return_value = {"sub": MOCK_CLIENT_ID_WITH_SUFFIX}
        yield mock_decode


@pytest.fixture
def mock_jwt_decode_no_suffix():
    """Mock JWT decode to return a client ID without @clients suffix."""
    with patch("jwt.decode") as mock_decode:
        mock_decode.return_value = {"sub": MOCK_CLIENT_ID}
        yield mock_decode


@pytest.fixture
def mock_jwt_decode_error():
    """Mock JWT decode to raise an error."""
    with patch("jwt.decode") as mock_decode:
        mock_decode.side_effect = jwt.InvalidTokenError("Invalid token")
        yield mock_decode


@pytest.fixture
def mock_visit_model():
    """Mock Visit database model."""
    with patch("policyengine_household_api.data.models.Visit") as MockVisit:
        visit_instance = MagicMock()
        MockVisit.return_value = visit_instance
        yield MockVisit, visit_instance


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch("policyengine_household_api.data.analytics_setup.db") as mock_db:
        session = MagicMock()
        session.add = MagicMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        mock_db.session = session
        yield session


@pytest.fixture
def mock_datetime():
    """Mock datetime to return a fixed time."""
    fixed_time = datetime(2024, 1, 1, 12, 0, 0)
    with patch(
        "policyengine_household_api.decorators.analytics.datetime"
    ) as mock_dt:
        mock_dt.utcnow.return_value = fixed_time
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        yield mock_dt, fixed_time


@pytest.fixture
def mock_constants_version():
    """Mock API version constant."""
    with patch(
        "policyengine_household_api.decorators.analytics.VERSION",
        MOCK_API_VERSION,
    ):
        yield MOCK_API_VERSION


@pytest.fixture
def mock_analytics_enabled():
    """Mock analytics as enabled."""
    with patch(
        "policyengine_household_api.data.analytics_setup.is_analytics_enabled"
    ) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_analytics_disabled():
    """Mock analytics as disabled."""
    with patch(
        "policyengine_household_api.data.analytics_setup.is_analytics_enabled"
    ) as mock:
        mock.return_value = False
        yield mock


@pytest.fixture
def mock_analytics_error():
    """Mock analytics check to raise an error."""
    with patch(
        "policyengine_household_api.data.analytics_setup.is_analytics_enabled"
    ) as mock:
        mock.side_effect = Exception("Cannot determine analytics status")
        yield mock


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
