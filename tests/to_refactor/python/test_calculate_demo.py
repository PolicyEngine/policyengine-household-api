import pytest
import os
from tests.to_refactor.fixtures import client
from policyengine_household_api.api import app


def test_calc_demo(client):
    """
    Ensure that calculate_demo properly calculates;
    the rate limiter does not return a 4xx, but instead
    waits until the rate limit has ended, preventing the
    need for a further test
    """

    response = client.post(
        "/us/calculate_demo",
        headers={
            "Content-Type": "application/json",
        },
        data=open(
            "./tests/to_refactor/python/data/calculate_us_1_data.json",
            "r",
            encoding="utf-8",
        ),
    )
    assert response.status_code == 200, response.text
