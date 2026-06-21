import json
from types import SimpleNamespace

from flask import Flask
import pytest

from policyengine_household_api.observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    current_context,
    init_observability,
    observability_runtime,
    segment,
)
import policyengine_household_api.observability as observability
from policyengine_household_api.observability.runtime import (
    INTERNAL_LOGGER,
    REQUEST_LOGGER,
    ObservabilityRuntime,
    RequestObservabilityContext,
    set_observability_runtime,
)
from policyengine_household_api.observability.config import (
    ObservabilityConfig,
)


class OTelFailure(BaseException):
    pass


def _observed_app():
    app = Flask(__name__)
    init_observability(app, service_role="test_api")

    @app.get("/ok")
    def ok():
        with segment("test_segment"):
            return {"status": "ok"}

    return app


def test_request_log_contains_request_metadata_and_timing(monkeypatch):
    records = []
    monkeypatch.setattr(REQUEST_LOGGER, "info", records.append)

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
    monkeypatch.setattr(REQUEST_LOGGER, "info", records.append)

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
    monkeypatch.setattr(REQUEST_LOGGER, "info", records.append)
    app = Flask(__name__)
    init_observability(app, service_role="test_api")

    @app.get("/context")
    def context_route():
        assert current_context() is not None
        return {"status": "ok"}

    assert app.test_client().get("/context").status_code == 200


def test_start_request_extracts_trace_context_from_flask_headers(monkeypatch):
    monkeypatch.setattr(REQUEST_LOGGER, "info", lambda _record: None)
    app = Flask(__name__)
    init_observability(app, service_role="test_api")
    runtime = app.extensions["policyengine_observability"]
    seen = {}

    class FakePropagate:
        def extract(self, carrier):
            seen["traceparent"] = carrier.get("traceparent")
            return "parent-context"

    class SpanContextManager:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeTracer:
        def start_as_current_span(self, _name, **kwargs):
            seen["context"] = kwargs["context"]
            return SpanContextManager()

    runtime.propagate = FakePropagate()
    runtime.tracer = FakeTracer()
    runtime.SpanKind = SimpleNamespace(SERVER="server")

    @app.get("/context")
    def context_route():
        return {"status": "ok"}

    response = app.test_client().get(
        "/context",
        headers={
            "Traceparent": (
                "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
            )
        },
    )

    assert response.status_code == 200
    assert seen["traceparent"].startswith("00-4bf92f")
    assert seen["context"] == "parent-context"


def test_segment_metric_includes_explicit_backend_attributes(monkeypatch):
    class Recorder:
        def __init__(self):
            self.records = []

        def record(self, duration, attributes):
            self.records.append((duration, attributes))

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
    runtime = ObservabilityRuntime(
        ObservabilityConfig(service_role="test_api")
    )
    runtime.enabled = True
    runtime.segment_duration = Recorder()
    runtime.backend_duration = Recorder()
    monkeypatch.setattr(runtime, "current_context", lambda: context)
    set_observability_runtime(runtime)

    with segment("modal_remote_execution", backend="modal"):
        pass

    segment_attributes = runtime.segment_duration.records[0][1]
    backend_attributes = runtime.backend_duration.records[0][1]
    assert segment_attributes["segment"] == "modal_remote_execution"
    assert segment_attributes["backend"] == "modal"
    assert backend_attributes["segment"] == "modal_remote_execution"
    assert backend_attributes["backend"] == "modal"


def test_segment_logs_and_swallows_otel_span_enter_failure(monkeypatch):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)

    class BrokenSpan:
        def __enter__(self):
            raise OTelFailure("otel enter failed")

        def __exit__(self, *_args):
            return None

    runtime = ObservabilityRuntime(
        ObservabilityConfig(service_role="test_api")
    )
    runtime.enabled = True
    runtime.tracer = SimpleNamespace(
        start_as_current_span=lambda *_args, **_kwargs: BrokenSpan()
    )
    set_observability_runtime(runtime)

    with segment("broken_span"):
        pass

    assert any("otel.span_enter" in log for log in internal_logs)
    assert any("otel enter failed" in log for log in internal_logs)


def test_segment_preserves_app_exception_when_otel_exit_fails(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)

    class BrokenExitSpan:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            raise OTelFailure("otel exit failed")

    runtime = ObservabilityRuntime(
        ObservabilityConfig(service_role="test_api")
    )
    runtime.enabled = True
    runtime.tracer = SimpleNamespace(
        start_as_current_span=lambda *_args, **_kwargs: BrokenExitSpan()
    )
    set_observability_runtime(runtime)

    with pytest.raises(ValueError, match="application failed"):
        with segment("broken_exit"):
            raise ValueError("application failed")

    assert any("otel.span_exit" in log for log in internal_logs)
    assert any("otel exit failed" in log for log in internal_logs)


def test_segment_preserves_app_exception_when_metric_recording_fails(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)
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
    runtime = ObservabilityRuntime(
        ObservabilityConfig(service_role="test_api")
    )
    runtime.enabled = True
    monkeypatch.setattr(runtime, "current_context", lambda: context)
    monkeypatch.setattr(
        runtime,
        "record_segment_metric",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OTelFailure("metrics failed")
        ),
    )
    set_observability_runtime(runtime)

    with pytest.raises(ValueError, match="application failed"):
        with segment("metric_failure"):
            raise ValueError("application failed")

    assert context.timings_ms["metric_failure"] >= 0
    assert any("request.record_segment" in log for log in internal_logs)
    assert any("metrics failed" in log for log in internal_logs)


def test_observability_failure_logging_falls_back_to_stderr(
    monkeypatch,
    capsys,
):
    runtime = ObservabilityRuntime(
        ObservabilityConfig(service_role="test_api")
    )

    def fail_logger(_record):
        raise OTelFailure("logger failed")

    monkeypatch.setattr(INTERNAL_LOGGER, "error", fail_logger)

    runtime.log_observability_failure(
        "otel.test_operation",
        OTelFailure("otel failed"),
    )

    captured = capsys.readouterr()
    assert "otel.test_operation" in captured.err
    assert "otel failed" in captured.err


def test_disabled_runtime_is_noop(monkeypatch):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)
    runtime = ObservabilityRuntime(ObservabilityConfig(enabled=False))
    set_observability_runtime(runtime)

    with segment("disabled"):
        pass
    observability.set_attribute("country_id", "us")
    observability.record_event("disabled_event")
    observability.record_error(
        RuntimeError("disabled"),
        handled=True,
        status_code=500,
    )

    assert observability_runtime() is runtime
    assert observability.traceparent_header() is None
    assert internal_logs == []


def test_public_api_excludes_removed_helper_names():
    assert "segment" in observability.__all__
    assert "set_attribute" in observability.__all__
    assert "traceparent_header" in observability.__all__
    removed_names = [
        "timed" + "_segment",
        "set_request" + "_attribute",
        "current_traceparent" + "_header",
    ]
    for name in removed_names:
        assert name not in observability.__all__
        assert not hasattr(observability, name)
