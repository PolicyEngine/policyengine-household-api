from datetime import datetime
import json
import logging

import pytest
from flask import Flask

from policyengine_household_api.decorators.auth import ANALYTICS_READ_SCOPE
from policyengine_household_analytics import analytics_setup
from policyengine_household_analytics.analytics_setup import db
from policyengine_household_api.endpoints import analytics
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
    assert payload["requested_version"] is None
    assert payload["resolved_channel"] is None
    assert [request["request_uuid"] for request in payload["requests"]] == [
        included_request.request_uuid
    ]
    assert payload["requests"][0]["requested_version"] == "current"
    assert payload["requests"][0]["resolved_channel"] == "current"
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
    assert payload["client_id"] is None
    assert payload["requests"][0]["client_id"] == "test-client"


def test__calculate_analytics_requests__filters_by_client_id(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    # A sub-shaped identifier: interactive-user rows carry these, and
    # the pipe must round-trip through query parsing untouched.
    partner_request = add_calculate_analytics_request(
        "partner-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
        client_id="google-oauth2|partner-123",
    )
    add_calculate_analytics_request(
        "probe-request",
        datetime(2026, 5, 10, 13, 0, 0),
        [calculate_analytics_variable("age")],
        client_id="probe-client",
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?"
        "client_id=google-oauth2%7Cpartner-123&"
        "start_time=2026-05-07T00:00:00Z"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["client_id"] == "google-oauth2|partner-123"
    assert [request["request_uuid"] for request in payload["requests"]] == [
        partner_request.request_uuid
    ]
    assert payload["requests"][0]["client_id"] == "google-oauth2|partner-123"


def test__calculate_analytics_requests__unknown_client_id_matches_nothing(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    add_calculate_analytics_request(
        "partner-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?client_id=no-such-client"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["client_id"] == "no-such-client"
    assert payload["requests"] == []


def test__calculate_analytics_requests__blank_client_id_means_no_filter(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    add_calculate_analytics_request(
        "partner-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?client_id=%20%20"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    # Blank strips to None: unfiltered results and a null echo, so a
    # form that submits an empty field cannot silently match nothing.
    assert response.status_code == 200
    assert payload["client_id"] is None
    assert len(payload["requests"]) == 1


def test__calculate_analytics_requests__null_client_id_rows_serialize_and_filter(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    # Auth-disabled instances store NULL client_ids; those rows must
    # serialize as null and stay out of client-scoped views.
    add_calculate_analytics_request(
        "anonymous-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
        client_id=None,
    )
    add_calculate_analytics_request(
        "partner-request",
        datetime(2026, 5, 10, 13, 0, 0),
        [calculate_analytics_variable("age")],
        client_id="partner-client",
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests"
    ):
        unfiltered = get_calculate_analytics_requests()
    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?client_id=partner-client"
    ):
        filtered = get_calculate_analytics_requests()

    unfiltered_payload = json.loads(unfiltered.data)
    client_ids = {
        request["request_uuid"]: request["client_id"]
        for request in unfiltered_payload["requests"]
    }
    assert client_ids == {
        "anonymous-request": None,
        "partner-request": "partner-client",
    }
    filtered_payload = json.loads(filtered.data)
    assert [
        request["request_uuid"] for request in filtered_payload["requests"]
    ] == ["partner-request"]


def test__calculate_analytics_requests__unique_respects_client_id_filter(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    add_calculate_analytics_request(
        "partner-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
        client_id="partner-client",
    )
    add_calculate_analytics_request(
        "probe-request",
        datetime(2026, 5, 11, 12, 0, 0),
        [
            calculate_analytics_variable("age"),
            calculate_analytics_variable("employment_income"),
        ],
        client_id="probe-client",
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?unique=true&client_id=partner-client"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["client_id"] == "partner-client"
    assert [key["variable_name"] for key in payload["unique_keys"]] == ["age"]
    assert payload["unique_keys"][0]["request_count"] == 1
    assert payload["unique_keys"][0]["occurrence_count"] == 1


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
    assert payload["requested_version"] is None
    assert payload["resolved_channel"] is None
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


def test__calculate_analytics_requests__filters_by_modal_routing(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    add_calculate_analytics_request(
        "current-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
        requested_version="current",
        resolved_channel="current",
    )
    frontier_request = add_calculate_analytics_request(
        "frontier-request",
        datetime(2026, 5, 11, 12, 0, 0),
        [calculate_analytics_variable("employment_income")],
        requested_version="frontier",
        resolved_channel="frontier",
    )
    exact_request = add_calculate_analytics_request(
        "exact-request",
        datetime(2026, 5, 12, 12, 0, 0),
        [calculate_analytics_variable("ctc")],
        requested_version="1.691.1",
        resolved_channel="frontier",
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?resolved_channel=frontier"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["resolved_channel"] == "frontier"
    assert [request["request_uuid"] for request in payload["requests"]] == [
        exact_request.request_uuid,
        frontier_request.request_uuid,
    ]

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?requested_version=1.691.1"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["requested_version"] == "1.691.1"
    assert [request["request_uuid"] for request in payload["requests"]] == [
        exact_request.request_uuid,
    ]


def test__calculate_analytics_requests__unique_respects_modal_routing_filters(
    analytics_endpoint_app,
    add_calculate_analytics_request,
    calculate_analytics_variable,
):
    add_calculate_analytics_request(
        "current-request",
        datetime(2026, 5, 10, 12, 0, 0),
        [calculate_analytics_variable("age")],
        requested_version="current",
        resolved_channel="current",
    )
    add_calculate_analytics_request(
        "frontier-request",
        datetime(2026, 5, 11, 12, 0, 0),
        [calculate_analytics_variable("employment_income")],
        requested_version="frontier",
        resolved_channel="frontier",
    )

    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?unique=true&resolved_channel=frontier"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 200
    assert payload["unique"] is True
    assert payload["unique_keys"] == [
        {
            "variable_name": "employment_income",
            "entity_type": "person",
            "source": "household_input",
            "period_granularity": "year",
            "availability_status": "supported",
            "variable_name_truncated": False,
            "request_count": 1,
            "occurrence_count": 1,
            "first_seen": "2026-05-11T12:00:00Z",
            "last_seen": "2026-05-11T12:00:00Z",
        }
    ]


def test__calculate_analytics_requests__invalid_resolved_channel_returns_400(
    analytics_endpoint_app,
):
    with analytics_endpoint_app.test_request_context(
        "/analytics/calculate/requests?resolved_channel=stable"
    ):
        response = get_calculate_analytics_requests()

    payload = json.loads(response.data)
    assert response.status_code == 400
    assert payload["status"] == "error"
    assert "resolved_channel" in payload["message"]


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


def test__analytics_storage_check__initializes_storage_lazily(monkeypatch):
    calls = []
    app = Flask(__name__)

    monkeypatch.setattr(
        analytics,
        "is_analytics_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        analytics,
        "is_analytics_schema_ready",
        lambda: True,
    )
    monkeypatch.setattr(
        analytics,
        "initialize_analytics_db_if_enabled",
        lambda flask_app: calls.append(flask_app),
    )

    with app.app_context():
        response = analytics._analytics_storage_error_response()

    assert response is None
    assert calls == [app]
    assert (
        app.config[analytics.ANALYTICS_STORAGE_INITIALIZED_CONFIG_KEY] is True
    )


def test__analytics_storage_check__initialization_failure_returns_503(
    monkeypatch,
    caplog,
):
    app = Flask(__name__)

    def fail_initialize(_app):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        analytics,
        "is_analytics_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        analytics,
        "initialize_analytics_db_if_enabled",
        fail_initialize,
    )
    caplog.set_level(logging.WARNING, logger=analytics.__name__)

    with app.app_context():
        response = analytics._analytics_storage_error_response()

    payload = json.loads(response.data)
    assert response.status_code == 503
    assert payload == {
        "status": "error",
        "message": "Analytics storage is not ready.",
    }
    assert "Analytics storage is unavailable" in caplog.text


def test__calculate_analytics_requests__works_after_prior_request(
    tmp_path,
    monkeypatch,
):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{tmp_path / 'analytics.db'}"
    )
    db.init_app(app)

    monkeypatch.setattr(analytics, "is_analytics_enabled", lambda: True)
    monkeypatch.setattr(analytics_setup, "is_analytics_enabled", lambda: True)
    monkeypatch.setattr(
        analytics_setup,
        "check_analytics_schema_ready",
        lambda: True,
    )

    app.add_url_rule("/ping", "ping", lambda: "ok")
    app.add_url_rule(
        "/analytics/calculate/requests",
        "calculate_analytics_requests",
        get_calculate_analytics_requests,
        methods=["GET"],
    )

    with app.app_context():
        db.create_all()

    client = app.test_client()
    assert client.get("/ping").status_code == 200

    response = client.get("/analytics/calculate/requests")

    assert response.status_code == 200
    assert response.json["status"] == "ok"

    with app.app_context():
        db.session.remove()
        db.drop_all()


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


@pytest.mark.parametrize(
    "authorization_header",
    [
        f"Bearer {TEST_AUTH_TOKEN}-wrong",
        "Bearer not-a-valid-token",
        f"Basic {TEST_AUTH_TOKEN}",
        "Bearer",
    ],
)
def test__calculate_analytics_requests_route__malformed_or_wrong_token_returns_401(
    scoped_analytics_client_factory,
    authorization_header,
):
    client = scoped_analytics_client_factory(ANALYTICS_READ_SCOPE)

    response = client.get(
        "/analytics/calculate/requests",
        headers={"Authorization": authorization_header},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "scopes",
    [
        "read:calculate-analytics-extra",
        "prefix:read:calculate-analytics",
        "read:calculate",
    ],
)
def test__calculate_analytics_requests_route__deceptive_scope_returns_403(
    scoped_analytics_client_factory,
    scopes,
):
    client = scoped_analytics_client_factory(scopes)

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


def test__calculate_analytics_requests_route__token_with_scope_among_others_returns_200(
    scoped_analytics_client_factory,
):
    client = scoped_analytics_client_factory(
        f"openid profile {ANALYTICS_READ_SCOPE}"
    )

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
