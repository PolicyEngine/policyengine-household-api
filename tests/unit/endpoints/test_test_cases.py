"""Unit tests for the test-cases CRUD endpoints.

Verifies per-client_id scoping (one partner can never read or mutate
another's cases), validation, and that the audit log captures every
mutation.
"""

from __future__ import annotations

import json

import pytest
from flask import Flask

from policyengine_household_api.data.analytics_setup import db
from policyengine_household_api.data.models import TestCase, TestCaseAudit
from policyengine_household_api.endpoints.test_cases import (
    create_test_case,
    delete_test_case,
    get_test_case,
    list_test_cases,
    update_test_case,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_cases_app(tmp_path, monkeypatch):
    """Minimal Flask app with the in-memory SQLite analytics DB and the
    test-cases storage gating helpers stubbed to "ready"."""
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
        f"sqlite:///{tmp_path / 'test-cases.db'}"
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def call_as(monkeypatch):
    """Returns a function that stubs the bearer-token claim verification
    so handlers see the given ``client_id`` (and optional scopes) without
    going through Auth0."""

    def _stub(client_id: str | None, scopes: str = ""):
        def fake_verify(token):
            if client_id is None:
                return None
            return {"sub": f"{client_id}@clients", "scope": scopes}

        monkeypatch.setattr(
            "policyengine_household_api.endpoints.test_cases._verified_token_claims",
            fake_verify,
        )

    return _stub


def _request_context(app, *, method: str, body: dict | None = None):
    return app.test_request_context(
        method=method,
        json=body,
        headers={"Authorization": "Bearer test-token"},
    )


def _payload() -> dict:
    return {
        "people": {"adult": {"age": {"2025": 30}}},
        "households": {"household": {"members": ["adult"]}},
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test__create__persists_and_returns_201(test_cases_app, call_as):
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={
            "name": "Single filer",
            "description": "30-year-old, $30k income",
            "payload": _payload(),
        },
    ):
        response = create_test_case()

    body = json.loads(response.data)
    assert response.status_code == 201
    assert body["status"] == "ok"
    assert body["test_case"]["name"] == "Single filer"
    assert body["test_case"]["payload"] == _payload()
    assert body["test_case"]["id"] > 0

    # Persisted to the right client_id and audited.
    rows = db.session.query(TestCase).all()
    assert [r.client_id for r in rows] == ["acme"]
    audits = db.session.query(TestCaseAudit).all()
    assert [(a.action, a.actor_client_id) for a in audits] == [
        ("created", "acme")
    ]


@pytest.mark.parametrize(
    "body,expected_message_fragment",
    [
        ({"name": "", "payload": {}}, "non-empty string"),
        ({"name": "x", "payload": "not a dict"}, "JSON object"),
        ({"name": "x"}, "JSON object"),  # missing payload
        ({"payload": {}}, "non-empty string"),  # missing name
    ],
)
def test__create__rejects_invalid_input(
    test_cases_app, call_as, body, expected_message_fragment
):
    call_as("acme")
    with _request_context(test_cases_app, method="POST", body=body):
        response = create_test_case()
    assert response.status_code == 400
    assert expected_message_fragment in json.loads(response.data)["message"]


def test__create__rejects_unauthenticated_caller(test_cases_app, call_as):
    call_as(None)
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "x", "payload": _payload()},
    ):
        response = create_test_case()
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# List + scoping
# ---------------------------------------------------------------------------


def test__list__only_returns_callers_cases(test_cases_app, call_as):
    # acme creates two cases.
    call_as("acme")
    for name in ("acme-one", "acme-two"):
        with _request_context(
            test_cases_app,
            method="POST",
            body={"name": name, "payload": _payload()},
        ):
            create_test_case()

    # impactica creates a third case with the same name.
    call_as("impactica")
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "acme-one", "payload": _payload()},
    ):
        create_test_case()

    # impactica only sees their own.
    with _request_context(test_cases_app, method="GET"):
        response = list_test_cases()
    body = json.loads(response.data)
    assert response.status_code == 200
    assert {c["name"] for c in body["test_cases"]} == {"acme-one"}

    # acme only sees their two.
    call_as("acme")
    with _request_context(test_cases_app, method="GET"):
        response = list_test_cases()
    body = json.loads(response.data)
    assert {c["name"] for c in body["test_cases"]} == {
        "acme-one",
        "acme-two",
    }


# ---------------------------------------------------------------------------
# Get + update + delete: cross-client isolation
# ---------------------------------------------------------------------------


def test__get__rejects_other_clients_case(test_cases_app, call_as):
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "acme case", "payload": _payload()},
    ):
        created = json.loads(create_test_case().data)["test_case"]

    call_as("impactica")
    with _request_context(test_cases_app, method="GET"):
        response = get_test_case(created["id"])
    assert response.status_code == 404


def test__update__changes_only_allowed_fields(test_cases_app, call_as):
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={
            "name": "before",
            "description": "old",
            "payload": _payload(),
        },
    ):
        created = json.loads(create_test_case().data)["test_case"]

    new_payload = {
        "people": {"adult": {"age": {"2026": 31}}},
        "households": {"household": {"members": ["adult"]}},
    }
    with _request_context(
        test_cases_app,
        method="PUT",
        body={"name": "after", "payload": new_payload},
    ):
        response = update_test_case(created["id"])
    body = json.loads(response.data)
    assert response.status_code == 200
    assert body["test_case"]["name"] == "after"
    assert body["test_case"]["payload"] == new_payload
    # Description was not in the body, so it stays.
    assert body["test_case"]["description"] == "old"

    # Update audited.
    actions = [
        a.action for a in db.session.query(TestCaseAudit).order_by(TestCaseAudit.id)
    ]
    assert actions == ["created", "updated"]


def test__update__rejects_other_clients_case(test_cases_app, call_as):
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "acme", "payload": _payload()},
    ):
        created = json.loads(create_test_case().data)["test_case"]

    call_as("impactica")
    with _request_context(
        test_cases_app, method="PUT", body={"name": "stolen"}
    ):
        response = update_test_case(created["id"])
    assert response.status_code == 404
    # Still owned by acme with original name.
    row = db.session.get(TestCase, created["id"])
    assert row.client_id == "acme"
    assert row.name == "acme"


def test__delete__removes_row_and_audits(test_cases_app, call_as):
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "doomed", "payload": _payload()},
    ):
        created = json.loads(create_test_case().data)["test_case"]

    with _request_context(test_cases_app, method="DELETE"):
        response = delete_test_case(created["id"])
    assert response.status_code == 200
    assert db.session.get(TestCase, created["id"]) is None

    actions = [
        a.action for a in db.session.query(TestCaseAudit).order_by(TestCaseAudit.id)
    ]
    assert actions == ["created", "deleted"]
    # Audit retains the name even though the row is gone.
    deleted_audit = (
        db.session.query(TestCaseAudit).order_by(TestCaseAudit.id.desc()).first()
    )
    assert deleted_audit.name_snapshot == "doomed"


def test__delete__rejects_other_clients_case(test_cases_app, call_as):
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "acme", "payload": _payload()},
    ):
        created = json.loads(create_test_case().data)["test_case"]

    call_as("impactica")
    with _request_context(test_cases_app, method="DELETE"):
        response = delete_test_case(created["id"])
    assert response.status_code == 404
    assert db.session.get(TestCase, created["id"]) is not None


# ---------------------------------------------------------------------------
# Phase 2: as_client_id staff overlay
# ---------------------------------------------------------------------------


def _request_context_with_query(app, *, method: str, query: str):
    return app.test_request_context(
        path=f"/test-cases?{query}",
        method=method,
        headers={"Authorization": "Bearer test-token"},
    )


def test__as_client_id__rejected_without_staff_scope(
    test_cases_app, call_as
):
    # acme (a partner with no staff scope) tries to read impactica's data.
    call_as("acme")
    with _request_context_with_query(
        test_cases_app, method="GET", query="as_client_id=impactica"
    ):
        response = list_test_cases()
    assert response.status_code == 403
    assert "policyengine-staff" in json.loads(response.data)["message"]


def test__as_client_id__honored_for_staff_callers(test_cases_app, call_as):
    # Partner acme creates a case as themselves.
    call_as("acme")
    with _request_context(
        test_cases_app,
        method="POST",
        body={"name": "acme case", "payload": _payload()},
    ):
        create_test_case()

    # Staff caller lists with as_client_id=acme — sees acme's case.
    call_as("staff-user", scopes="policyengine-staff")
    with _request_context_with_query(
        test_cases_app, method="GET", query="as_client_id=acme"
    ):
        response = list_test_cases()
    body = json.loads(response.data)
    assert response.status_code == 200
    assert {c["name"] for c in body["test_cases"]} == {"acme case"}

    # Same staff caller with no as_client_id sees their own (empty) list.
    with _request_context(test_cases_app, method="GET"):
        response = list_test_cases()
    assert json.loads(response.data)["test_cases"] == []


def test__as_client_id__staff_create_records_actor_separately(
    test_cases_app, call_as
):
    # Staff creates a case on acme's behalf.
    call_as("staff-user", scopes="policyengine-staff")
    with test_cases_app.test_request_context(
        path="/test-cases?as_client_id=acme",
        method="POST",
        json={"name": "by staff", "payload": _payload()},
        headers={"Authorization": "Bearer test-token"},
    ):
        response = create_test_case()
    assert response.status_code == 201

    # The case is owned by acme; the audit captures staff as the actor.
    cases = db.session.query(TestCase).all()
    assert [c.client_id for c in cases] == ["acme"]
    audit = db.session.query(TestCaseAudit).one()
    assert audit.client_id == "acme"
    assert audit.actor_client_id == "staff-user"
    assert audit.action == "created"
