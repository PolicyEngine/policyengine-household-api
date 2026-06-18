import json

from flask import Flask

from policyengine_household_api.observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    current_context,
    init_observability,
    timed_segment,
)
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

    response = _observed_app().test_client().get(
        "/ok?secret=value",
        headers={
            "X-Forwarded-For": "203.0.113.1, 10.0.0.2",
            "User-Agent": "test-agent",
        },
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

    response = _observed_app().test_client().get(
        "/ok",
        headers={OBSERVABILITY_INTERNAL_DISPATCH_HEADER: "1"},
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
