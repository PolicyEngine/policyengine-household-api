"""
Unit tests for analytics_optional decorator.
Tests conditional analytics logging based on opt-in/opt-out configuration.
"""

import pytest
from datetime import datetime
from tests.fixtures.decorators.analytics import sample_function
from tests.fixtures.data.analytics_setup import reset_analytics_state
from tests.fixtures.decorators.analytics_patches import (
    mock_analytics_enabled,
    mock_analytics_disabled,
    mock_analytics_error,
    mock_visit_instance,
    mock_visit_class,
    mock_request_with_auth,
    mock_request_without_auth,
    mock_jwt_valid_with_suffix,
    mock_jwt_valid_without_suffix,
    mock_jwt_invalid,
    mock_datetime_fixed,
    mock_version,
    mock_db_session,
    mock_db_session_with_error,
    setup_analytics_decorator_test,
)


class TestAnalyticsDecorator:
    """Test the log_analytics_if_enabled decorator."""

    def test__given_analytics_disabled__decorator_skips_analytics_logging(
        self, sample_function, mock_analytics_disabled
    ):
        """Decorator should skip analytics when disabled."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        decorated = log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")
        assert result == "Result: arg1, arg2, test"

    def test__given_analytics_enabled_and_valid_auth__decorator_logs_visit(
        self, sample_function, setup_analytics_decorator_test
    ):
        """Decorator should log analytics when enabled with valid auth."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        decorated = log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"

        # Verify properties were set on Visit instance
        visit = setup_analytics_decorator_test["visit"]
        assert visit.client_id == "test-client"
        assert visit.endpoint == "calculate"
        assert visit.method == "POST"
        assert visit.content_length_bytes == 1024
        assert visit.datetime == setup_analytics_decorator_test["fixed_time"]
        assert visit.api_version == "1.0.0"

        # Verify database operations
        session = setup_analytics_decorator_test["session"]
        session.add.assert_called_once_with(visit)
        session.commit.assert_called_once()

    def test__given_no_authorization__decorator_logs_with_unknown_client(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_visit_class,
        mock_request_without_auth,
        mock_datetime_fixed,
        mock_version,
        mock_db_session,
    ):
        """Decorator should handle missing authorization by using 'unknown' client_id."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        _, visit_instance = mock_visit_class

        decorated = log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        # Should log with 'unknown' client_id when auth is missing
        assert visit_instance.client_id == "unknown"
        mock_db_session.add.assert_called_once_with(visit_instance)

    def test__given_jwt_decode_error__decorator_logs_with_unknown_client(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_visit_class,
        mock_request_with_auth,
        mock_jwt_invalid,
        mock_datetime_fixed,
        mock_version,
        mock_db_session,
    ):
        """Decorator should handle JWT decode errors by using 'unknown' client_id."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        _, visit_instance = mock_visit_class

        decorated = log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert visit_instance.client_id == "unknown"

    def test__given_client_id_with_suffix__decorator_strips_suffix(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_visit_class,
        mock_request_with_auth,
        mock_jwt_valid_with_suffix,
        mock_datetime_fixed,
        mock_version,
        mock_db_session,
    ):
        """Decorator should strip @clients suffix from client ID."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        _, visit_instance = mock_visit_class

        decorated = log_analytics_if_enabled(sample_function)
        decorated("arg1", "arg2")

        # Verify client_id had @clients suffix stripped
        assert visit_instance.client_id == "test-client"

    def test__given_client_id_without_suffix__decorator_preserves_id(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_visit_class,
        mock_request_with_auth,
        mock_jwt_valid_without_suffix,
        mock_datetime_fixed,
        mock_version,
        mock_db_session,
    ):
        """Decorator should preserve client ID without @clients suffix."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        _, visit_instance = mock_visit_class

        decorated = log_analytics_if_enabled(sample_function)
        decorated("arg1", "arg2")

        # Verify client_id preserved as-is
        assert visit_instance.client_id == "test-client"

    def test__given_database_error__decorator_continues_without_failing(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_visit_class,
        mock_request_with_auth,
        mock_jwt_valid_with_suffix,
        mock_datetime_fixed,
        mock_version,
        mock_db_session_with_error,
    ):
        """Decorator should handle database errors gracefully."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        decorated = log_analytics_if_enabled(sample_function)

        # Should not raise error, function should still execute
        result = decorated("arg1", "arg2", kwarg1="test")
        assert result == "Result: arg1, arg2, test"

    def test__given_analytics_check_raises_error__decorator_continues_normally(
        self, sample_function, mock_analytics_error
    ):
        """Decorator should handle analytics check errors gracefully."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        decorated = log_analytics_if_enabled(sample_function)

        # Should not raise error even if analytics check fails
        result = decorated("arg1", "arg2", kwarg1="test")
        assert result == "Result: arg1, arg2, test"

    def test__given_function_decorated__metadata_is_preserved(
        self, sample_function
    ):
        """Decorator should preserve the original function's metadata."""
        from policyengine_household_api.decorators.analytics import (
            log_analytics_if_enabled,
        )

        decorated = log_analytics_if_enabled(sample_function)

        assert decorated.__name__ == sample_function.__name__
        assert decorated.__doc__ == sample_function.__doc__
