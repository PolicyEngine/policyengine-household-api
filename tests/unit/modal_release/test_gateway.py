import json

from flask import Response

from policyengine_household_api.modal_release.gateway import (
    create_gateway_app,
)


def _manifest():
    return {
        "schema_version": 1,
        "current": {
            "app_name": "current-app",
            "package_versions": {"us": "1.0.0"},
            "deployed_at": "2026-01-01T00:00:00+00:00",
        },
        "frontier": {
            "app_name": "frontier-app",
            "package_versions": {"us": "2.0.0"},
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
    assert worker_requests[0][0] == "current-app"


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


def test_calculate_routes_exact_active_country_package_version():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/calculate",
        json={"version": "2.0.0", "household": {}},
    )

    assert response.status_code == 200
    assert worker_requests[0][0] == "frontier-app"


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


def test_ai_analysis_routes_to_current_worker():
    client, worker_requests = _client_with_dispatch()

    response = client.post(
        "/us/ai-analysis",
        json={"version": "frontier", "household": {}},
    )

    assert response.status_code == 200
    app_name, payload = worker_requests[0]
    assert app_name == "current-app"
    assert payload["path"] == "us/ai-analysis"
    assert "version" in json.loads(payload["body"])


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
