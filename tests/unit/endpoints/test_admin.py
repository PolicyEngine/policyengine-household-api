"""Unit tests for the staff-only admin endpoints."""

from __future__ import annotations

import json

import pytest
from flask import Flask

from policyengine_household_api.data.analytics_setup import db
from policyengine_household_api.endpoints.admin import (
    list_activity,
    list_partners,
)
from policyengine_household_api.endpoints.test_cases import create_test_case


@pytest.fixture
def admin_app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.admin.is_analytics_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.admin.is_analytics_schema_ready",
        lambda: True,
    )
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.test_cases.is_analytics_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "policyengine_household_api.endpoints.test_cases.is_analytics_schema_ready",
        lambda: True,
    )

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{tmp_path / 'admin.db'}"
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def call_as(monkeypatch):
    def _stub(client_id: str | None, scopes: str = ""):
        def fake(token):
            if client_id is None:
                return None
            return {"sub": f"{client_id}@clients", "scope": scopes}

        # admin.py and test_cases.py each hold their own reference to
        # the verifier (imported by name), so monkeypatching the source
        # module isn't enough — patch both targets explicitly.
        monkeypatch.setattr(
            "policyengine_household_api.endpoints.test_cases._verified_token_claims",
            fake,
        )
        monkeypatch.setattr(
            "policyengine_household_api.endpoints.admin._verified_token_claims",
            fake,
        )

    return _stub


def _ctx(app, *, path: str = "/admin/partners", method: str = "GET"):
    return app.test_request_context(
        path=path,
        method=method,
        headers={"Authorization": "Bearer token"},
    )


def _seed_two_partners(app, call_as):
    """Have two partners each create a test case so list_partners has
    something to aggregate."""
    call_as("acme")
    with _ctx(
        app,
        path="/test-cases",
        method="POST",
    ) as c:
        c.request.get_data = lambda *a, **k: json.dumps(
            {"name": "acme one", "payload": {"people": {}}}
        ).encode()
        create_test_case()

    call_as("impactica")
    with _ctx(
        app,
        path="/test-cases",
        method="POST",
    ) as c:
        c.request.get_data = lambda *a, **k: json.dumps(
            {"name": "impactica one", "payload": {"people": {}}}
        ).encode()
        create_test_case()


def test__partners__rejected_without_staff_scope(admin_app, call_as):
    call_as("acme")
    with _ctx(admin_app):
        response = list_partners()
    assert response.status_code == 403


def test__partners__lists_distinct_client_ids_with_counts(
    admin_app, call_as
):
    _seed_two_partners(admin_app, call_as)

    call_as("staff", scopes="policyengine-staff")
    with _ctx(admin_app):
        response = list_partners()
    body = json.loads(response.data)
    assert response.status_code == 200
    rows = {p["client_id"]: p for p in body["partners"]}
    assert set(rows.keys()) == {"acme", "impactica"}
    assert rows["acme"]["test_case_count"] == 1
    assert rows["impactica"]["test_case_count"] == 1
    # Both have a non-null last_activity ISO string.
    for p in body["partners"]:
        assert p["last_activity"].endswith("Z")


def test__activity__rejected_without_staff_scope(admin_app, call_as):
    call_as("acme")
    with _ctx(admin_app, path="/admin/activity"):
        response = list_activity()
    assert response.status_code == 403


def test__activity__returns_recent_audits_newest_first(admin_app, call_as):
    _seed_two_partners(admin_app, call_as)

    call_as("staff", scopes="policyengine-staff")
    with _ctx(admin_app, path="/admin/activity"):
        response = list_activity()
    body = json.loads(response.data)
    assert response.status_code == 200
    # Two creates, ordered newest-first by id desc.
    assert [e["client_id"] for e in body["events"]] == ["impactica", "acme"]
    assert all(e["action"] == "created" for e in body["events"])


def test__activity__filter_by_client_id(admin_app, call_as):
    _seed_two_partners(admin_app, call_as)

    call_as("staff", scopes="policyengine-staff")
    with _ctx(admin_app, path="/admin/activity?client_id=acme"):
        response = list_activity()
    body = json.loads(response.data)
    assert {e["client_id"] for e in body["events"]} == {"acme"}


def test__activity__limit_validation(admin_app, call_as):
    call_as("staff", scopes="policyengine-staff")
    with _ctx(admin_app, path="/admin/activity?limit=0"):
        response = list_activity()
    assert response.status_code == 400
    with _ctx(admin_app, path="/admin/activity?limit=abc"):
        response = list_activity()
    assert response.status_code == 400
