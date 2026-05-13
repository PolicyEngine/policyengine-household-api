from datetime import datetime
import json

from policyengine_household_api.decorators.auth import ANALYTICS_READ_SCOPE
from policyengine_household_api.endpoints.analytics import (
    get_calculate_analytics_requests,
)
from tests.fixtures.endpoints.analytics import TEST_AUTH_TOKEN


def test__calculate_analytics_requests__filters_by_time_window(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    old_request = add_calculate_analytics_request(
        "old-request",
        datetime(2026, 5, 1, 12, 0, 0),
        [calculate_analytics_variable("age")],
    )
    included_request = add_calculate_analytics_request(
        "included-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("employment_income")],
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?"
        "start_time=2026-05-07T00:00:00Z&"
        "end_time=2026-05-13T00:00:00Z"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["unique"] is False
    assert [request["request_uuid"] for request in payload["requests"]] == [
        included_request.request_uuid
    ]
    assert payload["requests"][0]["variables"] == [
        {
            "variable_name": "employment_income",
            "entity_type": "person",
            "source": "household_input",
            "period_granularity": "year",
            "entity_count": 1,
            "period_count": 1,
            "occurrence_count": 1,
            "availability_status": "supported",
            "variable_name_truncated": False,
        }
    ]
    assert old_request.request_uuid not in {
        request["request_uuid"] for request in payload["requests"]
    }
    assert "client_id" not in payload["requests"][0]


def test__calculate_analytics_requests__unique_returns_grouped_keys(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    add_calculate_analytics_request(
        "request-one",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age", occurrence_count=2)],
    )
    add_calculate_analytics_request(
        "request-two",
        datetime(2026, 5, 11, 12, 0, 0),
        [
            calculate_analytics_variable("age"),
            calculate_analytics_variable("bad_input", status="unsupported"),
        ],
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?unique=true"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["unique"] is True
    assert "requests" not in payload
    assert payload["unique_keys"] == [
        {
            "variable_name": "age",
            "entity_type": "person",
            "source": "household_input",
            "period_granularity": "year",
            "availability_status": "supported",
            "variable_name_truncated": False,
            "request_count": 2,
            "occurrence_count": 3,
            "first_seen": "2026-05-10T12:00:00Z",
            "last_seen": "2026-05-11T12:00:00Z",
        },
        {
            "variable_name": "bad_input",
            "entity_type": "person",
            "source": "household_input",
            "period_granularity": "year",
            "availability_status": "unsupported",
            "variable_name_truncated": False,
            "request_count": 1,
            "occurrence_count": 1,
            "first_seen": "2026-05-11T12:00:00Z",
            "last_seen": "2026-05-11T12:00:00Z",
        },
    ]


def test__calculate_analytics_requests__invalid_time_returns_400(
    analytics_endpoint_app,
):
    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?start_time=not-a-time"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 400
    assert payload["status"] == "error"
    assert "start_time" in payload["message"]


def test__calculate_analytics_requests__analytics_disabled_returns_503(
    analytics_endpoint_app,
    monkeypatch,
):
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.analytics.is_analytics_enabled",
        lambda: False,
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 503
    assert payload == {
        "status": "error",
        "message": "Analytics is not enabled for this API instance.",
    }


def test__calculate_analytics_requests__schema_not_ready_returns_503(
    analytics_endpoint_app,
    monkeypatch,
):
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.analytics."
        "is_analytics_schema_ready",
        lambda: False,
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 503
    assert payload == {
        "status": "error",
        "message": "Analytics storage is not ready.",
    }


def test__calculate_analytics_requests_route__missing_token_returns_401(
    scoped_analytics_client_factory,
):
    client = scoped_analytics_client_factory(ANALYTICS_READ_SCOPE)

    response = client.get("/analytics/calculate/requests")

    assert response.status_code == 401


def test__calculate_analytics_requests_route__token_without_scope_returns_403(
    scoped_analytics_client_factory,
):
    client = scoped_analytics_client_factory("")

    response = client.get(
        "/analytics/calculate/requests",
        headers={"Authorization": f"Bearer {TEST_AUTH_TOKEN}"},
    )

    assert response.status_code == 403


def test__calculate_analytics_requests_route__token_with_scope_returns_200(
    scoped_analytics_client_factory,
):
    client = scoped_analytics_client_factory(ANALYTICS_READ_SCOPE)

    response = client.get(
        "/analytics/calculate/requests",
        headers={"Authorization": f"Bearer {TEST_AUTH_TOKEN}"},
    )

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["requests"] == []


def test__normal_protected_route__token_without_analytics_scope_returns_200(
    scoped_analytics_client_factory,
):
    client = scoped_analytics_client_factory("")

    response = client.post(
        "/us/calculate",
        headers={"Authorization": f"Bearer {TEST_AUTH_TOKEN}"},
    )

    assert response.status_code == 200
