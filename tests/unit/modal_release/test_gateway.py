import json

from flask import Response
import modal
import pytest

from policyengine_household_api.modal_release.gateway import (
    create_gateway_app,
    load_modal_manifest,
)
from policyengine_household_api.modal_release.manifest import (
    MANIFEST_SCHEMA_VERSION,
)
from policyengine_household_api.modal_release.routing_metadata import (
    MODAL_ROUTING_PAYLOAD_KEY,
)
from policyengine_household_api.observability import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
)


def _manifest():
    return {
        "schema_version": 1,
        "current": {
            "app_name": "current-app",
            "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
            "deployed_at": "2026-01-01T00:00:00+00:00",
        },
        "frontier": {
            "app_name": "frontier-app",
            "package_versions": {"uk": "2.31.0", "us": "2.0.0"},
            "deployed_at": "2026-01-02T00:00:00+00:00",
        },
        "retired": [],
    }


def _client_with_dispatch(manifest=None):
    worker_requests = []

    def worker_request(app_name, payload):
        worker_requests.append((app_name, payload))
        return Response(
            json.dumps({"status": "ok", "app_name": app_name}),
            mimetype="application/json",
        )

    app = create_gateway_app(
        manifest_loader=manifest or _manifest,
        worker_request=worker_request,
    )
    return app.test_client(), worker_requests


def test_calculate_defaults_to_current():
    client, worker_requests = _client_with_dispatch()

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "current-app"
    assert payload[MODAL_ROUTING_PAYLOAD_KEY] == {
        "requested_version": "current",
        "resolved_channel": "current",
    }


def test_calculate_routes_frontier_and_strips_version():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate",
        json={"version": "frontier", "household": {}},
    )

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "frontier-app"
    assert "version" not in json.loads(payload["body"])
    assert payload[MODAL_ROUTING_PAYLOAD_KEY] == {
        "requested_version": "frontier",
        "resolved_channel": "frontier",
    }


def test_calculate_routes_exact_active_country_package_version():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate",
        json={"version": "2.0.0", "household": {}},
    )

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "frontier-app"
    assert "version" not in json.loads(payload["body"])
    assert payload[MODAL_ROUTING_PAYLOAD_KEY] == {
        "requested_version": "2.0.0",
        "resolved_channel": "frontier",
    }


def test_calculate_rejects_unknown_version():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate",
        json={"version": "9.9.9", "household": {}},
    )

    assert response.status_code == 400
    assert not worker_requests
    assert "9.9.9" in response.get_json()["message"]


def test_calculate_rejects_non_string_version():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate",
        json={"version": {"target": "frontier"}, "household": {}},
    )

    assert response.status_code == 400
    assert not worker_requests
    assert response.get_json()["message"] == "`version` must be a string"


def test_calculate_routes_malformed_json_to_current_without_rewriting_body():
    client, worker_requests = _client_with_dispatch()
    raw_body = b'{"version": "frontier",'

    response = client.post(
        "/us/calculate",
        data=raw_body,
        content_type="application/json",
    )

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "current-app"
    assert payload["body"] == raw_body


def test_calculate_routes_non_object_json_to_current_without_rewriting_body():
    client, worker_requests = _client_with_dispatch()
    raw_body = b'["frontier"]'

    response = client.post(
        "/us/calculate",
        data=raw_body,
        content_type="application/json",
    )

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "current-app"
    assert payload["body"] == raw_body


def test_calculate_rejects_default_request_when_current_is_missing():
    client, worker_requests = _client_with_dispatch(
        manifest=lambda: {**_manifest(), "current": None}
    )

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 400
    assert not worker_requests
    assert (
        "No `current` household API version" in response.get_json()["message"]
    )


def test_calculate_rejects_frontier_request_when_frontier_is_missing():
    client, worker_requests = _client_with_dispatch(
        manifest=lambda: {**_manifest(), "frontier": None}
    )

    response = client.post(
        "/us/calculate",
        json={"version": "frontier", "household": {}},
    )

    assert response.status_code == 400
    assert not worker_requests
    assert (
        "No `frontier` household API version" in response.get_json()["message"]
    )


def test_calculate_forwards_request_metadata_to_worker():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate?trace=true",
        json={"household": {}},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    _, payload = worker_requests[0]
    assert payload["method"] == "POST"
    assert payload["path"] == "us/calculate"
    assert payload["query_string"] == "trace=true"
    assert payload["headers"]["Authorization"] == "Bearer token"
    assert payload["headers"][REQUEST_ID_HEADER]
    assert payload["headers"][OBSERVABILITY_INTERNAL_DISPATCH_HEADER] == "1"
    assert payload[MODAL_ROUTING_PAYLOAD_KEY] == {
        "requested_version": "current",
        "resolved_channel": "current",
    }


def test_gateway_routing_metadata_is_not_taken_from_inbound_headers():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate",
        json={"household": {}},
        headers={
            "X-PolicyEngine-Requested-Version": "frontier",
            "X-PolicyEngine-Resolved-Channel": "frontier",
        },
    )

    assert response.status_code == 200
    _, payload = worker_requests[0]
    assert payload[MODAL_ROUTING_PAYLOAD_KEY] == {
        "requested_version": "current",
        "resolved_channel": "current",
    }


def test_non_calculate_country_route_routes_to_current_worker():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/metadata",
        json={"version": "frontier", "household": {}},
    )

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "current-app"
    assert payload["path"] == "us/metadata"
    assert "version" in json.loads(payload["body"])
    assert payload[MODAL_ROUTING_PAYLOAD_KEY] == {
        "requested_version": "current",
        "resolved_channel": "current",
    }


def test_non_country_route_routes_to_current_worker():
    client, worker_requests = _client_with_dispatch()

    response = client.get("/specification")

    assert response.status_code == 200
    assert worker_requests[0][0] == "current-app"
    assert worker_requests[0][1]["path"] == "specification"


def test_readiness_check_fails_when_current_is_missing():
    client, worker_requests = _client_with_dispatch(
        manifest=lambda: {**_manifest(), "current": None}
    )

    response = client.get("/readiness_check")

    assert response.status_code == 503
    assert not worker_requests
    assert response.get_json()["message"] == (
        "No current household API app is configured"
    )


def test_country_versions_rejects_unsupported_country():
    client, worker_requests = _client_with_dispatch()

    response = client.get("/versions/zz")

    assert response.status_code == 404
    assert not worker_requests
    assert response.get_json()["message"] == "Unsupported country `zz`"


def test_load_modal_manifest_does_not_create_missing_dict(monkeypatch):
    calls = []

    def from_name(name, *, create_if_missing):
        calls.append((name, create_if_missing))
        raise modal.exception.NotFoundError("not found")

    monkeypatch.setattr(modal.Dict, "from_name", from_name)

    manifest = load_modal_manifest()

    assert calls == [("household-api-release-manifest", False)]
    assert manifest == {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "current": None,
        "frontier": None,
        "retired": [],
    }


def test_load_modal_manifest_preserves_unexpected_modal_errors(monkeypatch):
    def from_name(name, *, create_if_missing):
        raise modal.exception.AuthError("auth failed")

    monkeypatch.setattr(modal.Dict, "from_name", from_name)

    with pytest.raises(modal.exception.AuthError):
        load_modal_manifest()


def test_call_worker_function_uses_class_when_available(monkeypatch):
    """When the worker exposes the new ``HouseholdWorker`` class, the
    gateway should dispatch through ``modal.Cls.from_name``."""
    from policyengine_household_api.modal_release import gateway

    captured = {}

    class _StubMethod:
        def remote(self, payload):
            captured["dispatched_via"] = "class"
            captured["payload"] = payload
            return {"status_code": 200, "body": b'{"status":"ok"}'}

    class _StubInstance:
        handle_household_request = _StubMethod()

    class _StubCls:
        def __call__(self):
            return _StubInstance()

    def fake_cls_from_name(app_name, class_name):
        captured["cls_app_name"] = app_name
        captured["class_name"] = class_name
        return _StubCls()

    def fake_function_from_name(app_name, function_name):
        captured["fallback_invoked"] = True
        raise AssertionError("Function fallback must not be invoked")

    monkeypatch.setattr(
        modal.Cls, "from_name", staticmethod(fake_cls_from_name)
    )
    monkeypatch.setattr(
        modal.Function, "from_name", staticmethod(fake_function_from_name)
    )

    response = gateway.call_worker_function(
        "frontier-app", {"household": {"foo": "bar"}}
    )

    assert response.status_code == 200
    assert captured["dispatched_via"] == "class"
    assert captured["cls_app_name"] == "frontier-app"
    assert captured["class_name"] == "HouseholdWorker"
    assert captured["payload"] == {"household": {"foo": "bar"}}
    assert "fallback_invoked" not in captured


def test_call_worker_function_falls_back_to_function_for_legacy_workers(
    monkeypatch,
):
    """During a release transition, the existing frontier worker gets
    promoted to current without a redeploy, so the current worker may
    still expose the pre-class ``handle_household_request`` function.
    The gateway must fall back to ``modal.Function.from_name`` when the
    class cannot be found."""
    from policyengine_household_api.modal_release import gateway

    captured = {}

    def fake_cls_from_name(app_name, class_name):
        raise modal.exception.NotFoundError(
            f"No class named `{class_name}` in app `{app_name}`"
        )

    class _StubFunction:
        def remote(self, payload):
            captured["dispatched_via"] = "function"
            captured["payload"] = payload
            return {"status_code": 200, "body": b'{"status":"ok"}'}

    def fake_function_from_name(app_name, function_name):
        captured["fn_app_name"] = app_name
        captured["function_name"] = function_name
        return _StubFunction()

    monkeypatch.setattr(
        modal.Cls, "from_name", staticmethod(fake_cls_from_name)
    )
    monkeypatch.setattr(
        modal.Function, "from_name", staticmethod(fake_function_from_name)
    )

    response = gateway.call_worker_function(
        "current-app", {"household": {"foo": "bar"}}
    )

    assert response.status_code == 200
    assert captured["dispatched_via"] == "function"
    assert captured["fn_app_name"] == "current-app"
    assert captured["function_name"] == "handle_household_request"
    assert captured["payload"] == {"household": {"foo": "bar"}}
