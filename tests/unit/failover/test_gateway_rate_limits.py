"""Per-caller request rate limits applied by the public Cloud Run gateway."""

import pytest

from policyengine_household_common.worker_dispatch import (
    GATEWAY_RATE_LIMITED_PAYLOAD_KEY,
)
from policyengine_household_failover.rate_limits import (
    GatewayRateLimitConfig,
    gateway_rate_limit_config_from_env,
)


CLIENT_A_AUTHORIZATION = "Bearer token-for-client-a"
CLIENT_B_AUTHORIZATION = "Bearer token-for-client-b"
CLIENT_IDS_BY_AUTHORIZATION = {
    CLIENT_A_AUTHORIZATION: "client-a",
    CLIENT_B_AUTHORIZATION: "client-b",
}
CALCULATE_LIMIT_PER_MINUTE = 60


def _post(gateway, path, *, authorization=None, forwarded_for=None):
    headers = {}
    if authorization is not None:
        headers["Authorization"] = authorization
    if forwarded_for is not None:
        headers["X-Forwarded-For"] = forwarded_for
    return gateway.client.post(path, json={}, headers=headers)


def _statuses(responses):
    return [response.status_code for response in responses]


def test_calculate_limit_counts_each_auth0_client_separately(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway(
        client_ids_by_authorization=CLIENT_IDS_BY_AUTHORIZATION
    )

    client_a_responses = [
        _post(
            gateway,
            "/us/calculate",
            authorization=CLIENT_A_AUTHORIZATION,
            forwarded_for="203.0.113.1",
        )
        for _ in range(CALCULATE_LIMIT_PER_MINUTE + 1)
    ]
    client_b_response = _post(
        gateway,
        "/us/calculate",
        authorization=CLIENT_B_AUTHORIZATION,
        forwarded_for="203.0.113.1",
    )

    assert _statuses(client_a_responses[:-1]) == [200] * 60
    assert client_a_responses[-1].status_code == 429
    assert client_b_response.status_code == 200


def test_rate_limited_request_is_not_forwarded_to_a_backend(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway(
        client_ids_by_authorization=CLIENT_IDS_BY_AUTHORIZATION
    )

    for _ in range(CALCULATE_LIMIT_PER_MINUTE + 1):
        _post(gateway, "/us/calculate", authorization=CLIENT_A_AUTHORIZATION)

    assert len(gateway.forwarded_paths) == CALCULATE_LIMIT_PER_MINUTE


def test_rate_limited_response_is_json_with_retry_after(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway()

    _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")
    limited = _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")

    assert limited.status_code == 429
    assert limited.get_json()["status"] == "error"
    assert limited.get_json()["code"] == "rate_limited"
    retry_after_seconds = int(limited.headers["Retry-After"])
    assert 1 <= retry_after_seconds <= 10


def test_limited_routes_report_remaining_requests(build_rate_limited_gateway):
    gateway = build_rate_limited_gateway(
        client_ids_by_authorization=CLIENT_IDS_BY_AUTHORIZATION
    )

    first = _post(
        gateway, "/us/calculate", authorization=CLIENT_A_AUTHORIZATION
    )
    second = _post(
        gateway, "/us/calculate", authorization=CLIENT_A_AUTHORIZATION
    )

    assert first.headers["X-RateLimit-Limit"] == "60"
    assert first.headers["X-RateLimit-Remaining"] == "59"
    assert second.headers["X-RateLimit-Remaining"] == "58"
    assert int(first.headers["X-RateLimit-Reset"]) > 0


def test_calculate_without_valid_token_is_counted_by_client_ip(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway(
        client_ids_by_authorization=CLIENT_IDS_BY_AUTHORIZATION
    )

    first_address_responses = [
        _post(
            gateway,
            "/us/calculate",
            authorization="Bearer not-a-valid-token",
            forwarded_for="203.0.113.1",
        )
        for _ in range(CALCULATE_LIMIT_PER_MINUTE + 1)
    ]
    second_address_response = _post(
        gateway,
        "/us/calculate",
        authorization="Bearer not-a-valid-token",
        forwarded_for="203.0.113.2",
    )
    valid_client_response = _post(
        gateway,
        "/us/calculate",
        authorization=CLIENT_A_AUTHORIZATION,
        forwarded_for="203.0.113.1",
    )

    assert first_address_responses[-1].status_code == 429
    assert second_address_response.status_code == 200
    assert valid_client_response.status_code == 200


def test_demo_limit_counts_each_client_ip_separately(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway()

    first = _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")
    repeated = _post(
        gateway, "/us/calculate_demo", forwarded_for="203.0.113.1"
    )
    other_address = _post(
        gateway, "/us/calculate_demo", forwarded_for="203.0.113.2"
    )

    assert first.status_code == 200
    assert repeated.status_code == 429
    assert other_address.status_code == 200


def test_demo_limit_ignores_forwarded_entries_the_caller_added(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway()

    first = _post(
        gateway,
        "/us/calculate_demo",
        forwarded_for="198.51.100.7, 203.0.113.1",
    )
    with_different_caller_entry = _post(
        gateway,
        "/us/calculate_demo",
        forwarded_for="198.51.100.8, 203.0.113.1",
    )

    assert first.status_code == 200
    assert with_different_caller_entry.status_code == 429


def test_trusted_proxy_count_selects_the_entry_before_the_load_balancer(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway(
        rate_limit_config=GatewayRateLimitConfig(trusted_proxy_count=2)
    )
    load_balancer_address = "34.120.0.1"

    first = _post(
        gateway,
        "/us/calculate_demo",
        forwarded_for=f"198.51.100.7, 203.0.113.1, {load_balancer_address}",
    )
    same_client = _post(
        gateway,
        "/us/calculate_demo",
        forwarded_for=f"198.51.100.8, 203.0.113.1, {load_balancer_address}",
    )
    other_client = _post(
        gateway,
        "/us/calculate_demo",
        forwarded_for=f"203.0.113.2, {load_balancer_address}",
    )

    assert first.status_code == 200
    assert same_client.status_code == 429
    assert other_client.status_code == 200


def test_zero_trusted_proxies_uses_the_connection_address(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway(
        rate_limit_config=GatewayRateLimitConfig(trusted_proxy_count=0)
    )

    first = _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")
    different_forwarded_entry = _post(
        gateway, "/us/calculate_demo", forwarded_for="203.0.113.2"
    )

    assert first.status_code == 200
    assert different_forwarded_entry.status_code == 429


def test_demo_and_calculate_limits_are_counted_separately(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway()

    _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")
    limited_demo = _post(
        gateway, "/us/calculate_demo", forwarded_for="203.0.113.1"
    )
    calculate = _post(gateway, "/us/calculate", forwarded_for="203.0.113.1")
    other_country_demo = _post(
        gateway, "/uk/calculate_demo", forwarded_for="203.0.113.1"
    )

    assert limited_demo.status_code == 429
    assert calculate.status_code == 200
    # Both countries' demo endpoints share one per-caller allowance, as the
    # worker's per-route limit did.
    assert other_country_demo.status_code == 429


def test_analytics_requests_limit_counts_each_auth0_client(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway(
        client_ids_by_authorization=CLIENT_IDS_BY_AUTHORIZATION
    )

    client_a_responses = [
        gateway.client.get(
            "/analytics/calculate/requests",
            headers={"Authorization": CLIENT_A_AUTHORIZATION},
        )
        for _ in range(CALCULATE_LIMIT_PER_MINUTE + 1)
    ]
    client_b_response = gateway.client.get(
        "/analytics/calculate/requests",
        headers={"Authorization": CLIENT_B_AUTHORIZATION},
    )

    assert client_a_responses[-1].status_code == 429
    assert client_b_response.status_code == 200


def test_unlimited_routes_are_not_counted(build_rate_limited_gateway):
    gateway = build_rate_limited_gateway()

    preflight_statuses = [
        gateway.client.options(
            "/us/calculate_demo",
            headers={"X-Forwarded-For": "203.0.113.1"},
        ).status_code
        for _ in range(2)
    ]
    liveness_statuses = [
        gateway.client.get("/liveness_check").status_code for _ in range(2)
    ]

    assert 429 not in preflight_statuses
    assert liveness_statuses == [200, 200]
    assert (
        "X-RateLimit-Limit"
        not in gateway.client.get("/liveness_check").headers
    )


def test_rate_limits_can_be_disabled(build_rate_limited_gateway):
    gateway = build_rate_limited_gateway(
        rate_limit_config=GatewayRateLimitConfig(enabled=False)
    )

    responses = [
        _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")
        for _ in range(3)
    ]

    assert _statuses(responses) == [200, 200, 200]


@pytest.mark.parametrize(
    ("environment", "expected_config"),
    [
        ({}, GatewayRateLimitConfig(enabled=True, trusted_proxy_count=1)),
        (
            {
                "HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED": "false",
                "HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT": "2",
            },
            GatewayRateLimitConfig(enabled=False, trusted_proxy_count=2),
        ),
        (
            {
                "HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED": "TRUE",
                "HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT": "0",
            },
            GatewayRateLimitConfig(enabled=True, trusted_proxy_count=0),
        ),
    ],
)
def test_rate_limit_config_reads_environment(
    monkeypatch, environment, expected_config
):
    monkeypatch.delenv("HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.delenv("HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    assert gateway_rate_limit_config_from_env() == expected_config


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED", "yes"),
        ("HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED", "0"),
        ("HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT", "-1"),
        ("HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT", "two"),
    ],
)
def test_rate_limit_config_rejects_invalid_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        gateway_rate_limit_config_from_env()


def test_analytics_head_requests_share_the_get_allowance(
    build_rate_limited_gateway,
):
    # Flask serves HEAD with the GET view, so HEAD must not bypass the limit.
    gateway = build_rate_limited_gateway(
        client_ids_by_authorization=CLIENT_IDS_BY_AUTHORIZATION
    )
    headers = {"Authorization": CLIENT_A_AUTHORIZATION}

    for _ in range(CALCULATE_LIMIT_PER_MINUTE):
        gateway.client.head("/analytics/calculate/requests", headers=headers)
    limited_get = gateway.client.get(
        "/analytics/calculate/requests", headers=headers
    )
    limited_head = gateway.client.head(
        "/analytics/calculate/requests", headers=headers
    )

    assert limited_get.status_code == 429
    assert limited_head.status_code == 429
    assert len(gateway.forwarded_paths) == CALCULATE_LIMIT_PER_MINUTE


def test_rate_limited_response_is_readable_by_cross_origin_pages(
    build_rate_limited_gateway,
):
    # The API documentation page calls calculate_demo from another origin.
    gateway = build_rate_limited_gateway()
    headers = {
        "Origin": "https://policyengine.org",
        "X-Forwarded-For": "203.0.113.1",
    }

    gateway.client.post("/us/calculate_demo", json={}, headers=headers)
    limited = gateway.client.post(
        "/us/calculate_demo", json={}, headers=headers
    )

    assert limited.status_code == 429
    assert (
        limited.headers["Access-Control-Allow-Origin"]
        == "https://policyengine.org"
    )
    assert "Origin" in limited.headers["Vary"]
    exposed_headers = limited.headers["Access-Control-Expose-Headers"]
    assert "Retry-After" in exposed_headers
    assert "X-RateLimit-Remaining" in exposed_headers


def test_rate_limited_response_without_origin_has_no_cors_headers(
    build_rate_limited_gateway,
):
    gateway = build_rate_limited_gateway()

    _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")
    limited = _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")

    assert limited.status_code == 429
    assert "Access-Control-Allow-Origin" not in limited.headers


@pytest.mark.parametrize("limits_enabled", [True, False])
def test_forwarded_requests_tell_workers_the_gateway_owns_rate_limits(
    build_rate_limited_gateway, limits_enabled
):
    gateway = build_rate_limited_gateway(
        rate_limit_config=GatewayRateLimitConfig(enabled=limits_enabled)
    )

    _post(gateway, "/us/calculate_demo", forwarded_for="203.0.113.1")

    assert gateway.forwarded_payloads[0][GATEWAY_RATE_LIMITED_PAYLOAD_KEY]
