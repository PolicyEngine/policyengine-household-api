import json
from unittest.mock import patch

import pytest
from flask import Response

from policyengine_household_api.api import app, limiter


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
