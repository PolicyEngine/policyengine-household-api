import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from flask import Flask
import pytest
from policyengine_observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    ObservabilityConfig,
    ObservabilityRuntime,
    REQUEST_ID_HEADER,
    RequestObservabilityContext,
    current_context,
    observability_runtime,
    record_error,
    record_event,
    segment,
    set_attribute,
    set_observability_runtime,
    traceparent_header,
)
from policyengine_observability.runtime import INTERNAL_LOGGER
from policyengine_observability.runtime import REQUEST_LOGGER
from policyengine_household_api.observability.flask import (
    HOUSEHOLD_METRIC_ATTRIBUTE_KEYS,
)
from policyengine_household_api.observability.flask import init_observability
from policyengine_household_api.observability.segments import SegmentName
import policyengine_household_api.observability as household_observability


class OTelFailure(BaseException):
    pass


class RecordingHistogram:
    def __init__(self):
        self.records = []

    def record(self, duration, attributes):
        self.records.append((duration, attributes))


def _observed_app():
    app = Flask(__name__)
    init_observability(app, service_role="test_api")

    @app.get("/ok")
    def ok():
        with segment(SegmentName.REQUEST_PARSE):
            return {"status": "ok"}

    return app


def _stderr_json_records(capture):
    captured = capture.readouterr()
    records = []
    for line in captured.err.splitlines():
        line = line.strip()
        if line.startswith("{"):
            records.append(json.loads(line))
    return records


def _find_record(records, **matches):
    for record in records:
        if all(record.get(key) == value for key, value in matches.items()):
            return record
    raise AssertionError(f"No stderr JSON record matched {matches}: {records}")


def test_observability_import_does_not_load_household_json_utils():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import policyengine_household_api.observability.flask; "
                "loaded = sorted("
                "name for name in sys.modules "
                "if name.startswith('policyengine_household_api.utils')"
                "); "
                "assert 'policyengine_household_api.utils.json' "
                "not in loaded, loaded; "
                "assert 'numpy' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


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
    assert payload["timings_ms"]["request_parse"] >= 0


def test_request_log_contains_runtime_metadata(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_SERVICE_ROLE", raising=False)
    monkeypatch.setenv("OBSERVABILITY_LOG_DESTINATIONS", "stdout")
    monkeypatch.setenv("OBSERVABILITY_PLATFORM", "google_cloud_run")
    monkeypatch.setenv("OBSERVABILITY_RUNTIME_ROLE", "cloud_run_gateway")
    monkeypatch.setenv("K_SERVICE", "household-api-gateway")
    monkeypatch.setenv("K_REVISION", "household-api-gateway-00001")
    monkeypatch.setenv("K_CONFIGURATION", "household-api-gateway")
    monkeypatch.setenv("OBSERVABILITY_GOOGLE_CLOUD_PROJECT", "central-logs")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "policyengine-test")

    records = []
    monkeypatch.setattr(REQUEST_LOGGER, "info", records.append)
    app = Flask(__name__)
    init_observability(app, service_role="failover_gateway")

    @app.get("/metadata")
    def metadata():
        return {"status": "ok"}

    response = app.test_client().get("/metadata")

    assert response.status_code == 200
    payload = json.loads(records[0])
    assert payload["platform"] == "google_cloud_run"
    assert payload["runtime_role"] == "cloud_run_gateway"
    assert payload["cloud_run_service"] == "household-api-gateway"
    assert payload["cloud_run_revision"] == "household-api-gateway-00001"
    assert payload["cloud_run_configuration"] == "household-api-gateway"
    assert payload["google_cloud_project"] == "central-logs"


def test_local_observability_defaults_to_stdout_logs(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_LOG_DESTINATIONS", raising=False)
    monkeypatch.delenv("OBSERVABILITY_PLATFORM", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("K_REVISION", raising=False)
    monkeypatch.delenv("MODAL_ENVIRONMENT", raising=False)
    monkeypatch.delenv("MODAL_TASK_ID", raising=False)
    monkeypatch.delenv("OBSERVABILITY_MODAL_APP_NAME", raising=False)

    app = Flask(__name__)
    init_observability(app, service_role="test_api")
    runtime = app.extensions["policyengine_observability"]

    assert runtime.config.log_destinations == ("stdout",)


def test_cloud_run_observability_defaults_to_google_logs(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_LOG_DESTINATIONS", raising=False)
    monkeypatch.delenv("OBSERVABILITY_PLATFORM", raising=False)
    monkeypatch.setenv("K_SERVICE", "household-api-gateway")

    app = Flask(__name__)
    init_observability(app, service_role="failover_gateway")
    runtime = app.extensions["policyengine_observability"]

    assert runtime.config.log_destinations == ("google_cloud_logging",)


def test_modal_observability_defaults_to_google_logs(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_LOG_DESTINATIONS", raising=False)
    monkeypatch.setenv("OBSERVABILITY_PLATFORM", "modal")
    monkeypatch.setenv("OBSERVABILITY_SERVICE_ROLE", "modal_worker")
    monkeypatch.setenv(
        "OBSERVABILITY_MODAL_APP_NAME",
        "policyengine-household-api-current",
    )
    monkeypatch.setenv(
        "OBSERVABILITY_MODAL_FUNCTION_NAME",
        "HouseholdWorker.handle_household_request",
    )

    app = Flask(__name__)
    init_observability(app, service_role="api")
    runtime = app.extensions["policyengine_observability"]

    assert runtime.config.log_destinations == ("google_cloud_logging",)


def test_observability_log_destination_env_overrides_deployed_default(
    monkeypatch,
):
    monkeypatch.setenv("OBSERVABILITY_LOG_DESTINATIONS", "stdout")
    monkeypatch.setenv("OBSERVABILITY_PLATFORM", "google_cloud_run")

    app = Flask(__name__)
    init_observability(app, service_role="failover_gateway")
    runtime = app.extensions["policyengine_observability"]

    assert runtime.config.log_destinations == ("stdout",)


def _runtime_with_context(monkeypatch):
    context = RequestObservabilityContext(
        config=ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
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
        ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
        segment_registry=SegmentName,
    )
    runtime.enabled = True
    monkeypatch.setattr(runtime, "current_context", lambda: context)
    set_observability_runtime(runtime)
    return runtime, context


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
        config=ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
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


def test_household_metric_keys_include_household_dimensions():
    app = Flask(__name__)
    init_observability(app, service_role="test_api")
    runtime = app.extensions["policyengine_observability"]

    for key in HOUSEHOLD_METRIC_ATTRIBUTE_KEYS:
        assert key in runtime.config.metric_attribute_keys


def test_household_observability_uses_shared_otel_default(monkeypatch):
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    monkeypatch.setenv("OBSERVABILITY_OTEL_ENABLED", "false")

    app = Flask(__name__)
    init_observability(app, service_role="test_api")
    runtime = app.extensions["policyengine_observability"]

    assert runtime.config.otel_enabled is True


def test_http_segment_metric_includes_operation_flavor_and_route(monkeypatch):
    monkeypatch.setattr(REQUEST_LOGGER, "info", lambda _record: None)
    app = Flask(__name__)
    init_observability(app, service_role="test_api")
    runtime = app.extensions["policyengine_observability"]
    runtime.segment_duration = RecordingHistogram()

    @app.get("/metric/<country_id>")
    def metric_route(country_id):
        set_attribute("country_id", country_id)
        with segment(SegmentName.CALCULATION, backend="modal"):
            pass
        return {"status": "ok"}

    response = app.test_client().get("/metric/uk")

    assert response.status_code == 200
    _duration, attributes = runtime.segment_duration.records[0]
    assert attributes["operation"] == "/metric/<country_id>"
    assert attributes["flavor"] == "http"
    assert attributes["route"] == "/metric/<country_id>"
    assert attributes["method"] == "GET"
    assert attributes["segment"] == "calculation"
    assert attributes["backend"] == "modal"
    assert attributes["country_id"] == "uk"


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
    runtime, context = _runtime_with_context(monkeypatch)
    runtime.segment_duration = RecordingHistogram()
    runtime.backend_duration = RecordingHistogram()

    with segment(SegmentName.MODAL_REMOTE_EXECUTION, backend="modal"):
        pass

    assert context.timings_ms["modal_remote_execution"] >= 0
    segment_attributes = runtime.segment_duration.records[0][1]
    backend_attributes = runtime.backend_duration.records[0][1]
    assert segment_attributes["segment"] == "modal_remote_execution"
    assert segment_attributes["backend"] == "modal"
    assert backend_attributes["segment"] == "modal_remote_execution"
    assert backend_attributes["backend"] == "modal"


def test_unregistered_segment_string_logs_and_records_string(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)
    _runtime, context = _runtime_with_context(monkeypatch)

    with segment("local_test_segment"):
        pass

    assert context.timings_ms["local_test_segment"] >= 0
    assert any("segment.coerce" in log for log in internal_logs)
    assert any("local_test_segment" in log for log in internal_logs)


def test_non_string_segment_logs_and_records_string(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)
    _runtime, context = _runtime_with_context(monkeypatch)

    class CustomSegment:
        def __str__(self):
            return "custom_segment"

    with segment(CustomSegment()):
        pass

    assert context.timings_ms["custom_segment"] >= 0
    assert any("segment.coerce" in log for log in internal_logs)
    assert any("custom_segment" in log for log in internal_logs)


def test_unprintable_segment_logs_and_records_unknown(
    monkeypatch,
):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)
    _runtime, context = _runtime_with_context(monkeypatch)

    class BrokenSegment:
        def __str__(self):
            raise OTelFailure("segment string failed")

    with segment(BrokenSegment()):
        pass

    assert context.timings_ms["unknown_segment"] >= 0
    assert any("segment.coerce" in log for log in internal_logs)
    assert any("unknown_segment" in log for log in internal_logs)


def test_segment_logs_and_swallows_otel_span_enter_failure(monkeypatch):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)

    class BrokenSpan:
        def __enter__(self):
            raise OTelFailure("otel enter failed")

        def __exit__(self, *_args):
            return None

    runtime = ObservabilityRuntime(
        ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
        segment_registry=SegmentName,
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
        ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
        segment_registry=SegmentName,
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
        config=ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
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
        ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
        segment_registry=SegmentName,
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


def test_observability_failure_logging_destination_failure_reaches_stderr(
    monkeypatch,
    capfd,
):
    runtime = ObservabilityRuntime(
        ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_api",
            span_prefix="household",
        ),
        segment_registry=SegmentName,
    )

    def fail_logger(_record):
        raise OTelFailure("logger failed")

    monkeypatch.setattr(INTERNAL_LOGGER, "error", fail_logger)

    runtime.log_observability_failure(
        "otel.test_operation",
        OTelFailure("otel failed"),
    )

    record = _find_record(
        _stderr_json_records(capfd),
        event="observability_internal_error",
    )
    assert record["error"]["type"] == "OTelFailure"
    if record["operation"] == "otel.test_operation":
        assert record["error"]["message"] == "otel failed"
    elif record["operation"] == "logging.destination_emit":
        assert record["error"]["message"] == "logger failed"
    else:
        raise AssertionError(record)


def test_disabled_runtime_is_noop(monkeypatch):
    internal_logs = []
    monkeypatch.setattr(INTERNAL_LOGGER, "error", internal_logs.append)
    runtime = ObservabilityRuntime(
        ObservabilityConfig(
            service_name="policyengine-household-api",
            enabled=False,
        ),
        segment_registry=SegmentName,
    )
    set_observability_runtime(runtime)

    with segment("disabled"):
        pass
    set_attribute("country_id", "us")
    record_event("disabled_event")
    record_error(
        RuntimeError("disabled"),
        handled=True,
        status_code=500,
    )

    assert observability_runtime() is runtime
    assert traceparent_header() is None
    assert internal_logs == []


def test_household_package_does_not_reexport_shared_runtime_helpers():
    assert not hasattr(household_observability, "segment")
    assert not hasattr(household_observability, "set_attribute")
    assert not hasattr(household_observability, "traceparent_header")


def test_production_segment_call_sites_use_registry():
    repo_root = Path(__file__).resolve().parents[3]
    violations = []
    for path in (repo_root / "policyengine_household_api").rglob("*.py"):
        if 'segment("' in path.read_text():
            violations.append(str(path.relative_to(repo_root)))

    assert violations == []
