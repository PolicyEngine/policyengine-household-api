import json
from unittest.mock import patch

import flask
import pytest
from flask import Response

import policyengine_household_api.api as api_module
from policyengine_household_api.api import app, limiter
from policyengine_household_common.config_loader import ConfigLoader


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _ok_response(*_args, **_kwargs):
    return Response("OK", status=200)


def test_calculate_demo_rate_limit_returns_429(client):
    with patch(
        "policyengine_household_api.api.get_calculate",
        side_effect=_ok_response,
    ):
        first = client.post("/us/calculate_demo")
        second = client.post("/us/calculate_demo")

    assert first.status_code == 200
    assert second.status_code == 429


def test_calculate_rate_limit_returns_429_after_sixty_requests(client):
    with patch(
        "policyengine_household_api.api.get_calculate",
        side_effect=_ok_response,
    ):
        responses = [client.post("/us/calculate") for _ in range(61)]

    assert [response.status_code for response in responses[:60]] == [200] * 60
    assert responses[60].status_code == 429


def test_rate_limits_can_be_disabled_with_environment(monkeypatch):
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("CONFIG_VALUE_SETTINGS", raising=False)
    monkeypatch.setenv("RATE_LIMIT__ENABLED", "false")
    config_loader = ConfigLoader(default_config_path="/nonexistent")
    monkeypatch.setattr(api_module, "get_config_value", config_loader.get)

    test_app = flask.Flask(__name__)
    test_limiter = api_module.create_rate_limiter(test_app)

    @test_app.post("/")
    @test_limiter.limit("1 per minute")
    def limited_route():
        return "OK"

    with test_app.test_client() as test_client:
        statuses = [
            test_client.post("/").status_code,
            test_client.post("/").status_code,
        ]

    assert test_limiter.enabled is False
    assert statuses == [200, 200]


@pytest.mark.parametrize("invalid_value", ["false", 0, 1, None])
def test_rate_limit_setting_rejects_non_boolean(monkeypatch, invalid_value):
    monkeypatch.setattr(
        api_module,
        "get_config_value",
        lambda *_args, **_kwargs: invalid_value,
    )

    with pytest.raises(
        ValueError,
        match=r"rate_limit\.enabled must be a boolean",
    ):
        api_module.create_rate_limiter(flask.Flask(__name__))


def test_oversized_json_request_returns_413(client):
    original_limit = app.config["MAX_CONTENT_LENGTH"]
    app.config["MAX_CONTENT_LENGTH"] = 16

    try:
        response = client.post(
            "/us/calculate_demo",
            data=json.dumps(
                {
                    "household": {
                        "people": {
                            "you": {"age": {"2024": 40}},
                        }
                    }
                }
            ),
            content_type="application/json",
        )
    finally:
        app.config["MAX_CONTENT_LENGTH"] = original_limit

    assert response.status_code == 413
