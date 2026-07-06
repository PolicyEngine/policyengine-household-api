"""
Unit tests for the calculate analytics decorator.
"""

import logging

import pytest


class TestAnalyticsDecorator:
    """Test the log_analytics_if_enabled decorator."""

    def test__given_analytics_disabled__decorator_skips_analytics_logging(
        self,
        sample_function,
        mock_analytics_disabled,
        monkeypatch,
    ):
        """Decorator should skip analytics when disabled."""
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        decorated = analytics.log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert enqueue_calls == []

    def test__given_analytics_enabled_and_valid_auth__decorator_enqueues_event(
        self,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_with_suffix,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
    ):
        """Decorator should enqueue analytics when enabled with valid auth."""
        from policyengine_household_api.decorators import analytics

        class Response:
            status_code = 202

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        decorated = analytics.log_analytics_if_enabled(lambda: Response())
        response = decorated()

        assert response.status_code == 202
        assert len(enqueue_calls) == 1
        event = enqueue_calls[0]
        assert event.response_status_code == 202
        assert event.context.client_id == "test-client"
        assert event.context.endpoint == "calculate"
        assert event.context.method == "POST"
        assert event.context.content_length_bytes == 1024
        assert event.context.created_at == mock_datetime_fixed
        assert event.context.api_version == "1.0.0"

    def test__given_no_authorization__decorator_enqueues_null_client(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_request_without_auth,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
    ):
        """Missing Authorization header must store NULL client_id."""
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        decorated = analytics.log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert enqueue_calls[0].context.client_id is None

    def test__given_validated_token_sub_error__decorator_enqueues_null_client(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_error,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
    ):
        """Validated token sub extraction errors produce a NULL client_id."""
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        decorated = analytics.log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert enqueue_calls[0].context.client_id is None

    def test__given_client_id_without_suffix__decorator_preserves_id(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_without_suffix,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
    ):
        """Decorator should preserve client ID without @clients suffix."""
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        decorated = analytics.log_analytics_if_enabled(sample_function)
        decorated("arg1", "arg2")

        assert enqueue_calls[0].context.client_id == "test-client"

    def test__given_missing_validated_token_sub__decorator_enqueues_null_client(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_missing,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
    ):
        """Decorator should store null client_id when auth has no sub claim."""
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        decorated = analytics.log_analytics_if_enabled(sample_function)
        decorated("arg1", "arg2")

        assert enqueue_calls[0].context.client_id is None

    def test__given_authlib_validated_token__client_id_uses_sub_claim(self):
        from flask import Flask, g

        from policyengine_household_api.decorators import analytics

        app = Flask(__name__)
        with app.test_request_context(
            "/",
            headers={"Authorization": "Bearer untrusted-raw-token"},
        ):
            g.authlib_server_oauth2_token = {"sub": "validated-client@clients"}

            assert analytics._client_id_from_request() == "validated-client"

    def test__given_enqueue_error__decorator_logs_and_returns_response(
        self,
        sample_function,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_with_suffix,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
        caplog,
    ):
        """Cloud Tasks errors should not fail successful endpoint responses."""
        from policyengine_household_api.decorators import analytics

        def fail_enqueue(_event):
            raise RuntimeError("tasks unavailable")

        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            fail_enqueue,
        )
        caplog.set_level(logging.WARNING, logger=analytics.__name__)

        decorated = analytics.log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert "Failed to enqueue calculate analytics event" in caplog.text

    def test__given_context_build_error__decorator_logs_and_returns_response(
        self,
        sample_function,
        mock_analytics_enabled,
        monkeypatch,
        caplog,
    ):
        """Context-building errors should not fail endpoint responses."""
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "_build_analytics_context",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("bad request context")
            ),
        )
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )
        caplog.set_level(logging.WARNING, logger=analytics.__name__)

        decorated = analytics.log_analytics_if_enabled(sample_function)
        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert enqueue_calls == []
        assert "Failed to build analytics context" in caplog.text

    def test__given_analytics_check_raises_error__decorator_logs_and_returns(
        self,
        sample_function,
        mock_analytics_error,
        caplog,
    ):
        """Analytics status errors should fail open for user requests."""
        from policyengine_household_api.decorators import analytics

        caplog.set_level(logging.WARNING, logger=analytics.__name__)
        decorated = analytics.log_analytics_if_enabled(sample_function)

        result = decorated("arg1", "arg2", kwarg1="test")

        assert result == "Result: arg1, arg2, test"
        assert (
            "Failed to determine whether analytics is enabled" in caplog.text
        )

    def test__given_function_raises__enqueues_500_and_reraises(
        self,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_with_suffix,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
    ):
        from policyengine_household_api.decorators import analytics

        enqueue_calls = []
        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            enqueue_calls.append,
        )

        def fail():
            raise RuntimeError("calculation failed")

        decorated = analytics.log_analytics_if_enabled(fail)

        with pytest.raises(RuntimeError, match="calculation failed"):
            decorated()

        assert len(enqueue_calls) == 1
        assert enqueue_calls[0].response_status_code == 500

    def test__given_function_and_enqueue_raise__original_error_is_reraised(
        self,
        mock_analytics_enabled,
        mock_request_with_auth,
        mock_validated_token_sub_with_suffix,
        mock_datetime_fixed,
        mock_version,
        monkeypatch,
        caplog,
    ):
        from policyengine_household_api.decorators import analytics

        def fail_enqueue(_event):
            raise RuntimeError("tasks unavailable")

        def fail_endpoint():
            raise RuntimeError("calculation failed")

        monkeypatch.setattr(
            analytics,
            "enqueue_calculate_analytics_event",
            fail_enqueue,
        )
        caplog.set_level(logging.WARNING, logger=analytics.__name__)

        decorated = analytics.log_analytics_if_enabled(fail_endpoint)

        with pytest.raises(RuntimeError, match="calculation failed"):
            decorated()

        assert "Failed to enqueue calculate analytics event" in caplog.text

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
