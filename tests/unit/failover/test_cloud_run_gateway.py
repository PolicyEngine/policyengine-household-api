import concurrent.futures
import json
import sys
import threading
import types

from flask import Response
import pytest
from policyengine_observability import ObservabilityConfig
from policyengine_observability import ObservabilityRuntime
from policyengine_observability import RequestObservabilityContext

from policyengine_household_api.failover.cloud_run_gateway import (
    CircuitRegistry,
    FallbackBackendUnavailable,
    GcsFailoverManifestLoader,
    ModalCircuitPolicy,
    ModalBackendUnavailable,
    ModalExecutorSaturated,
    _modal_canary_confirms_outage,
    _run_modal_operation,
    call_cloud_run_worker,
    create_gateway_app,
    modal_status_summary,
    probe_modal_canary,
    probe_modal_worker,
    warm_cloud_run_worker,
)
from policyengine_household_api.failover.dispatch_codec import (
    encode_dispatch_response,
)
from policyengine_household_api.failover.manifest import (
    FailoverManifestError,
    FailoverManifestReadError,
    ResolvedFailoverChannel,
)


def _manifest():
    return {
        "schema_version": 1,
        "environment": "testing",
        "generated_at": "2026-06-03T00:00:00+00:00",
        "channels": {
            "current": {
                "modal_app_name": "modal-current",
                "cloud_run_worker_url": "https://current.run.app",
                "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
            },
            "frontier": {
                "modal_app_name": "modal-frontier",
                "cloud_run_worker_url": "https://frontier.run.app",
                "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
            },
        },
    }


def _json_response(payload, status=200):
    return Response(
        json.dumps(payload),
        status=status,
        mimetype="application/json",
    )


def _resolved_channel():
    return ResolvedFailoverChannel(
        channel="current",
        requested_version="current",
        modal_app_name="modal-current",
        cloud_run_worker_url="https://current.run.app",
        package_versions={"uk": "2.31.0", "us": "1.0.0"},
    )


def _client(
    *,
    clock=None,
    modal_request=None,
    modal_health_probe=None,
    modal_canary_probe=None,
    fallback_request=None,
    modal_status_checker=None,
    fallback_warmup=None,
    circuit_policy=None,
    modal_timeout_seconds=None,
    modal_request_timeout_seconds=None,
    modal_probe_timeout_seconds=None,
    modal_canary_timeout_seconds=None,
    manifest_loader=None,
):
    app = create_gateway_app(
        manifest_loader=manifest_loader or _manifest,
        modal_request=modal_request
        or (lambda app_name, payload: _json_response({"backend": "modal"})),
        modal_health_probe=modal_health_probe or (lambda app_name: None),
        modal_canary_probe=modal_canary_probe or (lambda: None),
        fallback_request=fallback_request
        or (
            lambda resolved, payload: _json_response({"backend": "cloud_run"})
        ),
        modal_status_checker=modal_status_checker or (lambda: {}),
        fallback_warmup=fallback_warmup or (lambda resolved: None),
        circuit_registry=CircuitRegistry(time_source=clock),
        circuit_policy=circuit_policy,
        modal_timeout_seconds=modal_timeout_seconds,
        modal_request_timeout_seconds=modal_request_timeout_seconds,
        modal_probe_timeout_seconds=modal_probe_timeout_seconds,
        modal_canary_timeout_seconds=modal_canary_timeout_seconds,
    )
    return app.test_client()


def _canary_failure():
    raise ModalBackendUnavailable("modal canary failed")


def test_gateway_routes_to_modal_when_health_probe_succeeds():
    response = _client().post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "modal"}
    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert response.headers["X-PolicyEngine-Primary-State"] == "healthy"
    assert response.headers["X-PolicyEngine-Route-Channel"] == "current"


def test_gateway_routes_to_fallback_after_threshold_and_canary_failure():
    status_checks = []
    warmups = []

    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=_canary_failure,
        modal_status_checker=lambda: status_checks.append("checked") or {},
        fallback_warmup=lambda resolved: warmups.append(resolved.channel),
    )

    for _ in range(9):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503
        assert response.headers["X-PolicyEngine-Backend"] == "none"

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "cloud_run"}
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert response.headers["X-PolicyEngine-Primary-State"] == "unhealthy"
    assert status_checks == ["checked"]
    assert warmups == ["current"]


def test_gateway_sends_slack_alerts_for_confirmed_fallback(monkeypatch):
    alerts = []
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        lambda event, **fields: alerts.append((event, fields)),
    )
    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=_canary_failure,
    )

    for _ in range(9):
        client.post("/us/calculate", json={"household": {}})
    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert alerts == [
        ("modal_circuit_opened", {"channel": "current"}),
        (
            "fallback_selected",
            {"reason": "modal_canary_confirmed", "channel": "current"},
        ),
    ]


def test_gateway_sends_slack_alert_for_forced_cloud_run_fallback(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_FAILOVER_FORCE_BACKEND", "cloud_run")
    alerts = []
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        lambda event, **fields: alerts.append((event, fields)),
    )

    response = _client().post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert alerts == [
        (
            "fallback_selected",
            {"reason": "forced_cloud_run", "channel": "current"},
        ),
    ]


def test_gateway_sends_slack_alert_when_fallback_is_unavailable(monkeypatch):
    alerts = []
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        lambda event, **fields: alerts.append((event, fields)),
    )
    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=_canary_failure,
        fallback_request=lambda resolved, payload: (_ for _ in ()).throw(
            FallbackBackendUnavailable("fallback failed")
        ),
    )

    for _ in range(10):
        response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.get_json()["code"] == "backend_unavailable"
    assert alerts[-1] == (
        "backend_unavailable",
        {"backend": "cloud_run", "channel": "current"},
    )


def test_gateway_does_not_send_slack_alert_for_modal_request_failure(
    monkeypatch,
):
    alerts = []
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        lambda event, **fields: alerts.append((event, fields)),
    )

    response = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
    ).post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert alerts == []


def test_gateway_sends_slack_alert_when_probe_opens_modal_circuit(monkeypatch):
    clock = [100.0]
    alerts = []

    def fail_probe(app_name):
        raise ModalBackendUnavailable("modal probe failed")

    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        lambda event, **fields: alerts.append((event, fields)),
    )
    client = _client(
        clock=lambda: clock[0],
        modal_health_probe=fail_probe,
        modal_canary_probe=_canary_failure,
        circuit_policy=ModalCircuitPolicy(
            failure_min_count=1,
            failure_rate=1,
            failure_window_seconds=60,
        ),
    )

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert alerts == [
        (
            "modal_circuit_opened",
            {"channel": "current", "source": "probe"},
        ),
        (
            "fallback_selected",
            {"reason": "modal_circuit_open", "channel": "current"},
        ),
    ]


def test_gateway_swallows_slack_alert_failure(monkeypatch):
    def fail_notification(event, **fields):
        raise RuntimeError("slack unavailable")

    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        fail_notification,
    )
    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=_canary_failure,
    )

    for _ in range(9):
        client.post("/us/calculate", json={"household": {}})
    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"


def test_app_level_500_does_not_trigger_fallback_or_status_page_check():
    status_checks = []
    fallback_calls = []

    client = _client(
        modal_request=lambda app_name, payload: _json_response(
            {"status": "error"},
            status=500,
        ),
        fallback_request=lambda resolved, payload: (
            fallback_calls.append(resolved.channel)
            or _json_response({"backend": "cloud_run"})
        ),
        modal_status_checker=lambda: status_checks.append("checked") or {},
    )

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 500
    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert response.headers["X-PolicyEngine-Primary-State"] == "healthy"
    assert fallback_calls == []
    assert status_checks == []


def test_forced_cloud_run_app_level_500_returns_response(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_FAILOVER_FORCE_BACKEND", "cloud_run")

    client = _client(
        fallback_request=lambda resolved, payload: _json_response(
            {"status": "error"},
            status=500,
        ),
    )

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 500
    assert response.get_json() == {"status": "error"}
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert response.headers["X-PolicyEngine-Primary-State"] == "healthy"


def test_modal_call_failure_needs_canary_failure_before_fallback():
    status_checks = []

    client = _client(
        modal_health_probe=lambda app_name: None,
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_status_checker=lambda: status_checks.append("checked") or {},
    )

    for _ in range(9):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "10"

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.headers["X-PolicyEngine-Backend"] == "none"
    assert status_checks == ["checked"]


def test_modal_timeout_failures_open_circuit_after_canary_failure():
    status_checks = []

    def timed_out_modal_request(app_name, payload):
        raise ModalBackendUnavailable("Modal operation timed out after 0.01s")

    client = _client(
        modal_request=timed_out_modal_request,
        modal_canary_probe=_canary_failure,
        modal_status_checker=lambda: status_checks.append("checked") or {},
        modal_request_timeout_seconds=0.01,
        modal_probe_timeout_seconds=1,
    )

    for _ in range(9):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "10"

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "cloud_run"}
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert response.headers["X-PolicyEngine-Primary-State"] == "unhealthy"
    assert status_checks == ["checked"]


def test_run_modal_operation_converts_timeout_to_modal_unavailable():
    release = threading.Event()

    try:
        with pytest.raises(ModalBackendUnavailable, match="timed out"):
            _run_modal_operation(
                lambda: release.wait(timeout=1),
                timeout_seconds=0.001,
            )
    finally:
        release.set()


def test_run_modal_operation_preserves_observability_context():
    runtime = ObservabilityRuntime(
        ObservabilityConfig(
            service_name="policyengine-household-api",
            service_role="test_gateway",
        )
    )
    context = RequestObservabilityContext(
        config=runtime.config,
        request_id="request-1",
        method="POST",
        route="/<path:path>",
        path="/uk/calculate",
        endpoint="route_request",
        query_keys=[],
        content_length_bytes=None,
        inbound={},
    )
    runtime.begin_request(context)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            result = _run_modal_operation(
                lambda: (
                    runtime.current_context() is context,
                    runtime.current_operation().name,
                    runtime.current_operation().flavor,
                ),
                timeout_seconds=1,
                executor=executor,
                semaphore=threading.BoundedSemaphore(1),
            )
    finally:
        runtime.teardown_request(None)

    assert result == (True, "/<path:path>", "http")


def test_modal_request_timeout_is_separate_from_probe_timeout():
    release = threading.Event()

    def slow_modal_request(app_name, payload):
        release.wait(timeout=0.02)
        return _json_response({"backend": "modal"})

    response = _client(
        modal_request=slow_modal_request,
        modal_request_timeout_seconds=1,
        modal_probe_timeout_seconds=0.001,
    ).post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "modal"}
    assert response.headers["X-PolicyEngine-Backend"] == "modal"


def test_both_backends_unavailable_returns_retry_after():
    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=_canary_failure,
        fallback_request=lambda resolved, payload: (_ for _ in ()).throw(
            FallbackBackendUnavailable("fallback failed")
        ),
    )

    for _ in range(10):
        response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert response.get_json()["code"] == "backend_unavailable"
    assert response.headers["X-PolicyEngine-Backend"] == "none"


def test_manifest_unavailable_returns_retry_after():
    def unavailable_manifest():
        raise FailoverManifestError("manifest could not be loaded")

    client = create_gateway_app(
        manifest_loader=unavailable_manifest,
        modal_request=lambda app_name, payload: _json_response(
            {"backend": "modal"}
        ),
        modal_health_probe=lambda app_name: None,
        fallback_request=lambda resolved, payload: _json_response(
            {"backend": "cloud_run"}
        ),
        modal_status_checker=lambda: {},
        fallback_warmup=lambda resolved: None,
    ).test_client()

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert response.get_json()["code"] == "gateway_unavailable"
    assert response.headers.get("X-PolicyEngine-Backend") is None


def test_gcs_manifest_loader_wraps_read_errors():
    loader = GcsFailoverManifestLoader(bucket_name="")

    with pytest.raises(FailoverManifestReadError, match="Could not read"):
        loader()


def test_cloud_run_worker_auth_failure_is_fallback_unavailable(monkeypatch):
    def fail_auth(audience):
        raise ValueError("token unavailable")

    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway._cloud_run_auth_header",
        fail_auth,
    )

    with pytest.raises(FallbackBackendUnavailable, match="token unavailable"):
        call_cloud_run_worker(
            _resolved_channel(),
            {
                "method": "GET",
                "path": "/liveness_check",
                "query_string": "",
                "headers": {},
                "body": b"",
            },
        )


def test_cloud_run_worker_timeout_uses_env(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                encode_dispatch_response(
                    {
                        "status_code": 200,
                        "body": b'{"backend":"cloud_run"}',
                        "headers": [("Content-Type", "application/json")],
                    }
                )
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("HOUSEHOLD_FAILOVER_DISABLE_CLOUD_RUN_AUTH", "1")
    monkeypatch.setenv(
        "HOUSEHOLD_FAILOVER_CLOUD_RUN_WORKER_TIMEOUT_SECONDS",
        "900",
    )
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway.urllib_request.urlopen",
        fake_urlopen,
    )

    response = call_cloud_run_worker(
        _resolved_channel(),
        {
            "method": "GET",
            "path": "/liveness_check",
            "query_string": "",
            "headers": {},
            "body": b"",
        },
    )

    assert response.status_code == 200
    assert captured["timeout"] == 900


def test_cloud_run_worker_returns_dispatched_500_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                encode_dispatch_response(
                    {
                        "status_code": 500,
                        "body": b'{"status":"error"}',
                        "headers": [("Content-Type", "application/json")],
                    }
                )
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        return FakeResponse()

    monkeypatch.setenv("HOUSEHOLD_FAILOVER_DISABLE_CLOUD_RUN_AUTH", "1")
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway.urllib_request.urlopen",
        fake_urlopen,
    )

    response = call_cloud_run_worker(
        _resolved_channel(),
        {
            "method": "POST",
            "path": "/us/calculate",
            "query_string": "",
            "headers": {},
            "body": b"{}",
        },
    )

    assert response.status_code == 500
    assert response.get_data(as_text=True) == '{"status":"error"}'


def test_cloud_run_worker_warmup_swallows_auth_failure(monkeypatch):
    def fail_auth(audience):
        raise ValueError("token unavailable")

    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway._cloud_run_auth_header",
        fail_auth,
    )

    warm_cloud_run_worker(_resolved_channel())


def test_probe_modal_worker_uses_liveness_dispatch(monkeypatch):
    captured_payloads = _install_fake_modal(
        monkeypatch,
        class_result={"status_code": 200, "body": b"OK", "headers": []},
    )

    probe_modal_worker("modal-current")

    assert captured_payloads == [
        {
            "method": "GET",
            "path": "/liveness_check",
            "query_string": "",
            "headers": {},
            "body": b"",
        }
    ]


def test_probe_modal_worker_liveness_supports_legacy_function(monkeypatch):
    captured_payloads = _install_fake_modal(
        monkeypatch,
        function_result={"status_code": 200, "body": b"OK", "headers": []},
    )

    probe_modal_worker("modal-current")

    assert captured_payloads[0]["path"] == "/liveness_check"


def test_probe_modal_canary_uses_configured_modal_app(monkeypatch):
    captured = {}

    class FakeModalFunction:
        @staticmethod
        def from_name(app_name, object_name, **kwargs):
            captured["app_name"] = app_name
            captured["object_name"] = object_name
            captured["kwargs"] = kwargs
            return types.SimpleNamespace(remote=lambda: {"ok": True})

    monkeypatch.setenv("MODAL_ENVIRONMENT", "testing")
    monkeypatch.setenv("HOUSEHOLD_MODAL_CANARY_APP_NAME", "custom-canary")
    monkeypatch.setenv(
        "HOUSEHOLD_FAILOVER_MODAL_CANARY_FUNCTION_NAME",
        "custom_ping",
    )
    monkeypatch.setitem(
        sys.modules,
        "modal",
        types.SimpleNamespace(Function=FakeModalFunction),
    )

    probe_modal_canary()

    assert captured == {
        "app_name": "custom-canary",
        "object_name": "custom_ping",
        "kwargs": {"environment_name": "testing"},
    }


def test_unknown_exact_package_version_returns_unprocessable_entity():
    response = _client().post(
        "/us/calculate",
        json={"version": "9.9.9", "household": {}},
    )

    assert response.status_code == 422
    assert "Retry-After" not in response.headers
    assert response.get_json() == {
        "status": "error",
        "code": "unsupported_version",
        "message": (
            "No active failover channel serves `us` package version `9.9.9`"
        ),
        "requested_version": "9.9.9",
        "country_id": "us",
        "available_versions": {"current": "1.0.0", "frontier": "2.0.0"},
    }


def test_inactive_exact_package_version_returns_unprocessable_entity():
    response = _client().post(
        "/us/calculate",
        json={"version": "0.9.0", "household": {}},
    )

    assert response.status_code == 422
    assert "Retry-After" not in response.headers
    assert response.get_json() == {
        "status": "error",
        "code": "unsupported_version",
        "message": (
            "No active failover channel serves `us` package version `0.9.0`"
        ),
        "requested_version": "0.9.0",
        "country_id": "us",
        "available_versions": {"current": "1.0.0", "frontier": "2.0.0"},
    }


def test_non_string_version_stays_bad_request():
    response = _client().post(
        "/us/calculate",
        json={"version": 123, "household": {}},
    )

    assert response.status_code == 400
    assert "Retry-After" not in response.headers
    assert response.get_json()["status"] == "error"


def test_forced_cloud_run_failure_returns_retry_after(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_FAILOVER_FORCE_BACKEND", "cloud_run")

    response = _client(
        fallback_request=lambda resolved, payload: (_ for _ in ()).throw(
            FallbackBackendUnavailable("fallback failed")
        )
    ).post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert response.get_json()["code"] == "backend_unavailable"
    assert response.headers["X-PolicyEngine-Backend"] == "none"


def test_forced_modal_does_not_fall_back_after_threshold(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_FAILOVER_FORCE_BACKEND", "modal")
    fallback_calls = []
    canary_calls = []

    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=lambda: canary_calls.append("canary"),
        fallback_request=lambda resolved, payload: (
            fallback_calls.append(resolved.channel)
            or _json_response({"backend": "cloud_run"})
        ),
    )

    for _ in range(10):
        response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.headers["X-PolicyEngine-Backend"] == "none"
    assert fallback_calls == []
    assert canary_calls == []


def test_status_page_is_not_checked_for_single_probe_failure():
    status_checks = []

    def fail_probe(app_name):
        raise ModalBackendUnavailable("modal probe failed")

    response = _client(
        modal_health_probe=fail_probe,
        modal_status_checker=lambda: status_checks.append("checked") or {},
    ).post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert status_checks == []


def test_status_page_failure_does_not_prevent_canary_confirmed_fallback():
    def fail_status_page():
        raise OSError("status page unavailable")

    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_canary_probe=_canary_failure,
        modal_status_checker=fail_status_page,
    )

    for _ in range(9):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"


def test_modal_failure_rate_must_cross_threshold_before_canary_check():
    clock = [100.0]
    policy = ModalCircuitPolicy(
        failure_min_count=10,
        failure_rate=0.5,
        failure_window_seconds=60,
    )
    registry = CircuitRegistry(time_source=lambda: clock[0])

    for _ in range(11):
        registry.record_success("current", policy)
    for _ in range(10):
        should_check = registry.record_failure("current", policy)

    assert should_check is False


def test_open_circuit_recovers_after_repeated_canary_and_worker_successes():
    clock = [100.0]
    modal_calls = []
    canary_calls = []
    registry = CircuitRegistry(time_source=lambda: clock[0])
    open_client = create_gateway_app(
        manifest_loader=_manifest,
        modal_request=lambda app_name, payload: (
            modal_calls.append(app_name)
            or _json_response({"backend": "modal"})
        ),
        modal_health_probe=lambda app_name: None,
        modal_canary_probe=lambda: canary_calls.append("canary"),
        fallback_request=lambda resolved, payload: _json_response(
            {"backend": "cloud_run"}
        ),
        modal_status_checker=lambda: {},
        fallback_warmup=lambda resolved: None,
        circuit_registry=registry,
        circuit_policy=ModalCircuitPolicy(
            failure_min_count=1,
            failure_rate=1,
            failure_window_seconds=60,
            min_open_seconds=60,
            recovery_successes=3,
        ),
    ).test_client()
    registry.open("current")

    response = open_client.post("/us/calculate", json={"household": {}})
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"

    clock[0] = 161.0
    for _ in range(2):
        clock[0] += 16
        response = open_client.post("/us/calculate", json={"household": {}})
        assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"

    clock[0] += 16
    response = open_client.post("/us/calculate", json={"household": {}})

    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert len(canary_calls) == 3


def test_gateway_sends_slack_alert_when_modal_circuit_recovers(monkeypatch):
    clock = [100.0]
    registry = CircuitRegistry(time_source=lambda: clock[0])
    registry.open("current")
    alerts = []
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "notify_failover_lifecycle_event",
        lambda event, **fields: alerts.append((event, fields)),
    )
    client = create_gateway_app(
        manifest_loader=_manifest,
        modal_request=lambda app_name, payload: _json_response(
            {"backend": "modal"}
        ),
        modal_health_probe=lambda app_name: None,
        modal_canary_probe=lambda: None,
        fallback_request=lambda resolved, payload: _json_response(
            {"backend": "cloud_run"}
        ),
        modal_status_checker=lambda: {},
        fallback_warmup=lambda resolved: None,
        circuit_registry=registry,
        circuit_policy=ModalCircuitPolicy(
            min_open_seconds=60,
            recovery_successes=1,
        ),
    ).test_client()

    clock[0] = 200.0
    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert alerts == [
        ("modal_circuit_recovered", {"channel": "current"}),
    ]


def test_modal_status_summary_keeps_only_relevant_status_fields():
    summary = modal_status_summary(
        {
            "data": {"attributes": {"aggregate_state": "degraded"}},
            "included": [
                {
                    "type": "status_page_resource",
                    "attributes": {
                        "public_name": "CPU functions",
                        "status": "degraded",
                    },
                },
                {
                    "type": "status_page_resource",
                    "attributes": {
                        "public_name": "Storage",
                        "status": "operational",
                    },
                },
                {
                    "type": "status_page_resource",
                    "attributes": {
                        "public_name": "Web endpoints",
                        "status": "downtime",
                    },
                },
            ],
        }
    )

    assert summary == {
        "aggregate_state": "degraded",
        "resources": {
            "CPU functions": "degraded",
            "Web endpoints": "downtime",
        },
    }


def test_exact_package_version_routes_to_matching_channel():
    captured = []

    client = _client(
        modal_request=lambda app_name, payload: (
            captured.append(app_name) or _json_response({"backend": "modal"})
        )
    )

    response = client.post(
        "/us/calculate",
        json={"version": "2.0.0", "household": {}},
    )

    assert response.status_code == 200
    assert captured == ["modal-frontier"]
    assert response.headers["X-PolicyEngine-Route-Channel"] == "frontier"


def test_versions_endpoint_omits_worker_urls_and_matches_modal_schema():
    response = _client().get("/versions")

    assert response.status_code == 200
    assert response.get_json() == {
        "schema_version": 1,
        "current": {
            "app_name": "modal-current",
            "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
        },
        "frontier": {
            "app_name": "modal-frontier",
            "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
        },
    }
    body = response.get_data(as_text=True)
    assert "cloud_run_worker_url" not in body
    assert "run.app" not in body
    assert "retired" not in body


def test_gateway_rejects_request_body_over_limit(monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_FAILOVER_MAX_CONTENT_LENGTH", "1024")

    response = _client().post(
        "/us/calculate",
        data=b"x" * 4096,
        content_type="application/json",
    )

    assert response.status_code == 413


def test_gcs_manifest_loader_serves_last_known_good_on_refresh_error():
    clock = [1000.0]
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 1:
            return _manifest()
        raise RuntimeError("gcs unavailable")

    loader = GcsFailoverManifestLoader(
        bucket_name="bucket",
        cache_seconds=30,
        time_source=lambda: clock[0],
        fetch=fetch,
    )

    first = loader()
    assert first["channels"]["current"]["modal_app_name"] == "modal-current"

    clock[0] += 31  # expire the cache so the next call refreshes
    second = loader()
    assert second == first  # stale manifest served instead of raising
    assert len(calls) == 2

    clock[0] += 1  # within the refreshed window: serve cache, no new fetch
    third = loader()
    assert third == first
    assert len(calls) == 2


def test_gcs_manifest_loader_raises_when_no_cached_manifest():
    def fetch():
        raise RuntimeError("gcs unavailable")

    loader = GcsFailoverManifestLoader(bucket_name="bucket", fetch=fetch)

    with pytest.raises(FailoverManifestReadError, match="Could not read"):
        loader()


def test_run_modal_operation_raises_saturated_when_executor_full():
    semaphore = threading.BoundedSemaphore(1)
    assert semaphore.acquire(blocking=False) is True
    try:
        with pytest.raises(ModalExecutorSaturated):
            _run_modal_operation(
                lambda: None,
                timeout_seconds=1,
                semaphore=semaphore,
            )
    finally:
        semaphore.release()


def test_modal_canary_saturation_does_not_confirm_outage(monkeypatch):
    # A fully drained probe executor means the canary cannot run; local
    # saturation must not be treated as confirmation of a Modal outage.
    drained = threading.BoundedSemaphore(1)
    assert drained.acquire(blocking=False) is True
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "_MODAL_PROBE_EXECUTOR_SEMAPHORE",
        drained,
    )

    confirmed = _modal_canary_confirms_outage(
        probe_canary=_canary_failure,
        timeout_seconds=1,
    )

    assert confirmed is False


def test_request_executor_saturation_sheds_load_without_opening_circuit():
    fallback_calls = []
    canary_calls = []

    def saturated_modal(app_name, payload):
        raise ModalExecutorSaturated("Modal operation executor is saturated")

    client = _client(
        modal_request=saturated_modal,
        modal_canary_probe=lambda: canary_calls.append("canary"),
        fallback_request=lambda resolved, payload: (
            fallback_calls.append(resolved.channel)
            or _json_response({"backend": "cloud_run"})
        ),
    )

    for _ in range(15):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503
        assert response.headers["X-PolicyEngine-Backend"] == "none"
        assert response.headers["X-PolicyEngine-Primary-State"] == "healthy"

    # Local saturation never records circuit failures, so it neither runs the
    # canary nor trips the breaker into the Cloud Run fallback.
    assert fallback_calls == []
    assert canary_calls == []


def test_recovery_probe_saturation_preserves_recovery_progress(monkeypatch):
    clock = [100.0]
    registry = CircuitRegistry(time_source=lambda: clock[0])
    policy = ModalCircuitPolicy(
        min_open_seconds=60,
        recovery_successes=3,
    )
    registry.open("current")
    registry.record_recovery_success("current", policy)
    assert registry.state("current").recovery_successes == 1

    drained = threading.BoundedSemaphore(1)
    assert drained.acquire(blocking=False) is True
    monkeypatch.setattr(
        "policyengine_household_api.failover.cloud_run_gateway."
        "_MODAL_PROBE_EXECUTOR_SEMAPHORE",
        drained,
    )

    client = create_gateway_app(
        manifest_loader=_manifest,
        modal_request=lambda app_name, payload: _json_response(
            {"backend": "modal"}
        ),
        modal_health_probe=lambda app_name: None,
        modal_canary_probe=lambda: None,
        fallback_request=lambda resolved, payload: _json_response(
            {"backend": "cloud_run"}
        ),
        modal_status_checker=lambda: {},
        fallback_warmup=lambda resolved: None,
        circuit_registry=registry,
        circuit_policy=policy,
    ).test_client()

    clock[0] = 200.0  # past both min_open_seconds and the probe interval
    response = client.post("/us/calculate", json={"household": {}})

    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    # A saturated recovery probe must not reset the recovery streak.
    assert registry.state("current").recovery_successes == 1


def _install_fake_modal(
    monkeypatch,
    *,
    class_result=None,
    function_result=None,
):
    captured_payloads = []

    class NotFoundError(Exception):
        pass

    class FakeModalCls:
        @staticmethod
        def from_name(app_name, object_name, **kwargs):
            if class_result is None:
                raise NotFoundError()

            class FakeWorkerClass:
                def __call__(self):
                    return types.SimpleNamespace(
                        handle_household_request=types.SimpleNamespace(
                            remote=lambda payload: (
                                captured_payloads.append(payload)
                                or class_result
                            )
                        )
                    )

            return FakeWorkerClass()

    class FakeModalFunction:
        @staticmethod
        def from_name(app_name, object_name, **kwargs):
            return types.SimpleNamespace(
                remote=lambda payload: (
                    captured_payloads.append(payload) or function_result
                )
            )

    fake_modal = types.SimpleNamespace(
        Cls=FakeModalCls,
        Function=FakeModalFunction,
        exception=types.SimpleNamespace(NotFoundError=NotFoundError),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    return captured_payloads
