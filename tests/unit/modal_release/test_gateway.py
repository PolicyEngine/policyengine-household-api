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


def _client_with_proxy():
    proxied_requests = []

    def proxy(app_name, body):
        proxied_requests.append((app_name, body))
        return Response(
            json.dumps({"status": "ok", "app_name": app_name}),
            mimetype="application/json",
        )

    app = create_gateway_app(
        manifest_loader=_manifest,
        proxy_request=proxy,
    )
    return app.test_client(), proxied_requests


def test_calculate_defaults_to_current():
    client, proxied_requests = _client_with_proxy()

    response = client.post("/us/calculate", json={"household": {}})

    assert response.status_code == 200
    assert proxied_requests[0][0] == "current-app"


def test_calculate_routes_frontier_and_strips_version():
    client, proxied_requests = _client_with_proxy()

    response = client.post(
        "/us/calculate",
        json={"version": "frontier", "household": {}},
    )

    assert response.status_code == 200
    app_name, body = proxied_requests[0]
    assert app_name == "frontier-app"
    assert "version" not in json.loads(body)


def test_calculate_routes_exact_active_country_package_version():
    client, proxied_requests = _client_with_proxy()

    response = client.post(
        "/us/calculate",
        json={"version": "2.0.0", "household": {}},
    )

    assert response.status_code == 200
    assert proxied_requests[0][0] == "frontier-app"


def test_calculate_rejects_unknown_version():
    client, proxied_requests = _client_with_proxy()

    response = client.post(
        "/us/calculate",
        json={"version": "9.9.9", "household": {}},
    )

    assert response.status_code == 400
    assert not proxied_requests
    assert "9.9.9" in response.get_json()["message"]
