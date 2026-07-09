from datetime import datetime

import pytest
from flask import Flask, Response

from policyengine_household_analytics.analytics_setup import db
from policyengine_household_analytics.orm import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)
from policyengine_household_api.decorators.auth import (
    ANALYTICS_READ_SCOPE,
    create_auth_decorator,
)
from policyengine_household_api.endpoints.analytics import (
    get_calculate_analytics_requests,
)


TEST_AUTH_TOKEN = "test-jwt-token"


@pytest.fixture
def analytics_endpoint_app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.analytics.is_analytics_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.analytics."
        "is_analytics_schema_ready",
        lambda: True,
    )

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{tmp_path / 'analytics.db'}"
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def add_calculate_analytics_request():
    return _add_calculate_analytics_request


@pytest.fixture
def calculate_analytics_variable():
    return _calculate_analytics_variable


@pytest.fixture
def scoped_analytics_client_factory(tmp_path, monkeypatch):
    apps = []

    def factory(scopes: str = ""):
        _patch_test_auth_config(monkeypatch, scopes)
        _patch_analytics_storage_ready(monkeypatch)

        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            f"sqlite:///{tmp_path / f'analytics-{len(apps)}.db'}"
        )
        db.init_app(app)

        auth = create_auth_decorator()
        app.add_url_rule(
            "/analytics/calculate/requests",
            "calculate_analytics_requests",
            auth([ANALYTICS_READ_SCOPE])(get_calculate_analytics_requests),
            methods=["GET"],
        )
        app.add_url_rule(
            "/us/calculate",
            "calculate",
            auth()(lambda: Response("ok", status=200)),
            methods=["POST"],
        )

        with app.app_context():
            db.create_all()

        apps.append(app)
        return app.test_client()

    yield factory

    for app in apps:
        with app.app_context():
            db.session.remove()
            db.drop_all()


def _add_calculate_analytics_request(
    request_uuid: str,
    created_at: datetime,
    variable_rows: list[dict],
    requested_version: str | None = "current",
    resolved_channel: str | None = "current",
    client_id: str | None = "test-client",
) -> CalculateRequest:
    visit = Visit()
    visit.client_id = client_id
    visit.datetime = created_at
    visit.api_version = "0.17.0"
    visit.endpoint = "calculate"
    visit.method = "POST"
    visit.content_length_bytes = 123
    db.session.add(visit)
    db.session.flush()

    calculate_request = CalculateRequest()
    calculate_request.visit_id = visit.id
    calculate_request.request_uuid = request_uuid
    calculate_request.client_id = client_id
    calculate_request.api_version = "0.17.0"
    calculate_request.country_id = "us"
    calculate_request.model_version = "1.691.1"
    calculate_request.requested_version = requested_version
    calculate_request.resolved_channel = resolved_channel
    calculate_request.endpoint = "calculate"
    calculate_request.method = "POST"
    calculate_request.content_length_bytes = 123
    calculate_request.response_status_code = 200
    calculate_request.distinct_variable_count = len(variable_rows)
    calculate_request.unsupported_variable_count = sum(
        variable["availability_status"] == "unsupported"
        for variable in variable_rows
    )
    calculate_request.deprecated_allowlisted_variable_count = 0
    calculate_request.created_at = created_at
    db.session.add(calculate_request)
    db.session.flush()

    for variable_row in variable_rows:
        variable = CalculateRequestVariable()
        variable.request_id = calculate_request.id
        variable.client_id = client_id
        variable.created_at = created_at
        variable.country_id = "us"
        variable.api_version = "0.17.0"
        variable.model_version = "1.691.1"
        variable.requested_version = requested_version
        variable.resolved_channel = resolved_channel
        variable.response_status_code = 200
        for key, value in variable_row.items():
            setattr(variable, key, value)
        db.session.add(variable)

    db.session.commit()
    return calculate_request


def _patch_test_auth_config(monkeypatch, scopes: str) -> None:
    def get_config_value(path: str, default=None):
        config = {
            "app.environment": "test_with_auth",
            "auth.enabled": True,
            "auth.auth0.address": "test-tenant.auth0.com",
            "auth.auth0.audience": "https://test-api-identifier",
            "auth.auth0.test_token": TEST_AUTH_TOKEN,
            "auth.auth0.test_token_scopes": scopes,
        }
        return config.get(path, default)

    monkeypatch.setattr(
        "policyengine_household_api.decorators.auth.get_config_value",
        get_config_value,
    )


def _patch_analytics_storage_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.analytics.is_analytics_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.analytics."
        "is_analytics_schema_ready",
        lambda: True,
    )


def _calculate_analytics_variable(
    variable_name: str,
    *,
    occurrence_count: int = 1,
    status: str = "supported",
) -> dict:
    return {
        "variable_name": variable_name,
        "variable_name_truncated": False,
        "entity_type": "person",
        "source": "household_input",
        "period_granularity": "year",
        "entity_count": 1,
        "period_count": 1,
        "occurrence_count": occurrence_count,
        "availability_status": status,
    }
