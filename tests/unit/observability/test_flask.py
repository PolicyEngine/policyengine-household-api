import json
from types import SimpleNamespace

from flask import Flask
import pytest

from policyengine_household_api.observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    current_context,
    init_observability,
    timed_segment,
)
from policyengine_household_api.observability import (
    request as request_observability,
)
from policyengine_household_api.observability.internal import _INTERNAL_LOGGER
from policyengine_household_api.observability.request import (
    RequestObservabilityContext,
)
from policyengine_household_api.observability.request import _REQUEST_LOGGER
from policyengine_household_api.observability.config import (
    ObservabilityConfig,
)


def _observed_app():
    app = Flask(__name__)
    init_observability(app, service_role="test_api")

    @app.get("/ok")
    def ok():
        with timed_segment("test_segment"):
            return {"status": "ok"}

    return app


def test_request_log_contains_request_metadata_and_timing(monkeypatch):
    records = []
    monkeypatch.setattr(_REQUEST_LOGGER, "info", records.append)

    response = (
        _observed_app()
        .test_client()
        .get(
            "/ok?secret=value",
            headers={
                "X-Forwarded-For": "203.0.113.1, 10.0.0.2",
                "User-Agent": "test-agent",
            },
        )
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]
    assert len(records) == 1
    payload = json.loads(records[0])
    assert payload["event"] == "http_request_completed"
    assert payload["service_role"] == "test_api"
    assert payload["route"] == "/ok"
    assert payload["query_keys"] == ["secret"]
    assert "value" not in records[0]
    assert payload["client_ip"] == "203.0.113.1"
    assert payload["forwarded_for"] == ["203.0.113.1", "10.0.0.2"]
    assert payload["timings_ms"]["test_segment"] >= 0


def test_internal_dispatch_suppresses_external_request_log(monkeypatch):
    records = []
    monkeypatch.setattr(_REQUEST_LOGGER, "info", records.append)

    response = (
        _observed_app()
        .test_client()
        .get(
            "/ok",
            headers={OBSERVABILITY_INTERNAL_DISPATCH_HEADER: "1"},
        )
    )

    assert response.status_code == 200
    assert records == []


def test_metric_attributes_exclude_high_cardinality_request_fields():
    context = RequestObservabilityContext(
        config=ObservabilityConfig(service_role="test_api"),
        request_id="req-123",
        method="GET",
        route="/ok",
        path="/ok",
        endpoint="ok",
        query_keys=[],
        content_length_bytes=None,
        inbound={
            "client_ip": "203.0.113.1",
            "user_agent": "test-agent",
        },
    )
    context.status_code = 200
    context.set_attribute("country_id", "us")
    context.set_attribute("backend", "modal")

    attributes = context.metric_attributes()

    assert attributes["route"] == "/ok"
    assert attributes["country_id"] == "us"
    assert attributes["backend"] == "modal"
    assert "request_id" not in attributes
    assert "client_ip" not in attributes
    assert "user_agent" not in attributes


def test_current_context_is_available_during_request(monkeypatch):
    records = []
    monkeypatch.setattr(_REQUEST_LOGGER, "info", records.append)
    app = Flask(__name__)
    init_observability(app, service_role="test_api")

    @app.get("/context")
    def context_route():
        assert current_context() is not None
        return {"status": "ok"}

    assert app.test_client().get("/context").status_code == 200


def test_timed_segment_logs_and_swallows_otel_span_enter_failure(monkeypatch):
    internal_logs = []
    monkeypatch.setattr(_INTERNAL_LOGGER, "error", internal_logs.append)

    class BrokenSpan:
        def __enter__(self):
            raise RuntimeError("otel enter failed")

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        request_observability,
        "trace",
        SimpleNamespace(
            get_tracer=lambda _name: SimpleNamespace(
                start_as_current_span=lambda *_args, **_kwargs: BrokenSpan()
            )
        ),
    )

    with timed_segment("broken_span"):
        pass

    assert any("otel.span_enter" in log for log in internal_logs)
    assert any("otel enter failed" in log for log in internal_logs)


def test_timed_segment_preserves_app_exception_when_otel_exit_fails(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(_INTERNAL_LOGGER, "error", internal_logs.append)

    class BrokenExitSpan:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            raise RuntimeError("otel exit failed")

    monkeypatch.setattr(
        request_observability,
        "trace",
        SimpleNamespace(
            get_tracer=lambda _name: SimpleNamespace(
                start_as_current_span=lambda *_args, **_kwargs: (
                    BrokenExitSpan()
                )
            )
        ),
    )

    with pytest.raises(ValueError, match="application failed"):
        with timed_segment("broken_exit"):
            raise ValueError("application failed")

    assert any("otel.span_exit" in log for log in internal_logs)
    assert any("otel exit failed" in log for log in internal_logs)


def test_timed_segment_preserves_app_exception_when_metric_recording_fails(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(_INTERNAL_LOGGER, "error", internal_logs.append)
    context = RequestObservabilityContext(
        config=ObservabilityConfig(service_role="test_api"),
        request_id="req-123",
        method="GET",
        route="/ok",
        path="/ok",
        endpoint="ok",
        query_keys=[],
        content_length_bytes=None,
        inbound={},
    )
    monkeypatch.setattr(
        request_observability,
        "current_context",
        lambda: context,
    )
    monkeypatch.setattr(
        request_observability.METRICS,
        "record_segment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("metrics failed")
        ),
    )

    with pytest.raises(ValueError, match="application failed"):
        with timed_segment("metric_failure"):
            raise ValueError("application failed")

    assert context.timings_ms["metric_failure"] >= 0
    assert any("request.record_segment" in log for log in internal_logs)
    assert any("metrics failed" in log for log in internal_logs)
