import json
import time

from flask import Response

from policyengine_household_api.failover.cloud_run_gateway import (
    CircuitRegistry,
    FallbackBackendUnavailable,
    ModalBackendUnavailable,
    create_gateway_app,
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


def _client(
    *,
    clock=None,
    modal_request=None,
    modal_health_probe=None,
    fallback_request=None,
    modal_status_checker=None,
    fallback_warmup=None,
    modal_timeout_seconds=None,
):
    app = create_gateway_app(
        manifest_loader=_manifest,
        modal_request=modal_request
        or (lambda app_name, payload: _json_response({"backend": "modal"})),
        modal_health_probe=modal_health_probe or (lambda app_name: None),
        fallback_request=fallback_request
        or (
            lambda resolved, payload: _json_response({"backend": "cloud_run"})
        ),
        modal_status_checker=modal_status_checker or (lambda: {}),
        fallback_warmup=fallback_warmup or (lambda resolved: None),
        circuit_registry=CircuitRegistry(time_source=clock),
        modal_timeout_seconds=modal_timeout_seconds,
    )
    return app.test_client()


def test_gateway_routes_to_modal_when_health_probe_succeeds():
    response = _client().post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "modal"}
    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert response.headers["X-PolicyEngine-Primary-State"] == "healthy"
    assert response.headers["X-PolicyEngine-Route-Channel"] == "current"


def test_gateway_routes_to_fallback_after_three_modal_failures():
    status_checks = []
    warmups = []

    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_status_checker=lambda: status_checks.append("checked") or {},
        fallback_warmup=lambda resolved: warmups.append(resolved.channel),
    )

    for _ in range(2):
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


def test_app_level_500_does_not_trigger_fallback_or_status_page_check():
    status_checks = []
    fallback_calls = []

    client = _client(
        modal_request=lambda app_name, payload: _json_response(
            {"status": "error"},
            status=500,
        ),
        fallback_request=lambda resolved, payload: fallback_calls.append(
            resolved.channel
        )
        or _json_response({"backend": "cloud_run"}),
        modal_status_checker=lambda: status_checks.append("checked") or {},
    )

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 500
    assert response.headers["X-PolicyEngine-Backend"] == "modal"
    assert response.headers["X-PolicyEngine-Primary-State"] == "healthy"
    assert fallback_calls == []
    assert status_checks == []


def test_modal_call_failure_opens_circuit_after_threshold_then_falls_back():
    status_checks = []

    client = _client(
        modal_health_probe=lambda app_name: None,
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        modal_status_checker=lambda: status_checks.append("checked") or {},
    )

    for _ in range(2):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "10"

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "cloud_run"}
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert status_checks == ["checked"]


def test_three_modal_timeouts_open_circuit_then_fall_back():
    status_checks = []

    def slow_modal_request(app_name, payload):
        time.sleep(0.05)
        return _json_response({"backend": "modal"})

    client = _client(
        modal_request=slow_modal_request,
        modal_status_checker=lambda: status_checks.append("checked") or {},
        modal_timeout_seconds=0.01,
    )

    for _ in range(2):
        response = client.post("/us/calculate", json={"household": {}})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "10"

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert response.get_json() == {"backend": "cloud_run"}
    assert response.headers["X-PolicyEngine-Backend"] == "cloud_run"
    assert response.headers["X-PolicyEngine-Primary-State"] == "unhealthy"
    assert status_checks == ["checked"]


def test_both_backends_unavailable_returns_retry_after():
    client = _client(
        modal_request=lambda app_name, payload: (_ for _ in ()).throw(
            ModalBackendUnavailable("modal failed")
        ),
        fallback_request=lambda resolved, payload: (_ for _ in ()).throw(
            FallbackBackendUnavailable("fallback failed")
        ),
    )

    for _ in range(3):
        response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert response.get_json()["code"] == "backend_unavailable"
    assert response.headers["X-PolicyEngine-Backend"] == "none"


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


def test_exact_package_version_routes_to_matching_channel():
    captured = []

    client = _client(
        modal_request=lambda app_name, payload: captured.append(app_name)
        or _json_response({"backend": "modal"})
    )

    response = client.post(
        "/us/calculate",
        json={"version": "2.0.0", "household": {}},
    )

    assert response.status_code == 200
    assert captured == ["modal-frontier"]
    assert response.headers["X-PolicyEngine-Route-Channel"] == "frontier"
