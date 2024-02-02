import pytest
import os
from .utils import client
from policyengine_household_api.api import app


class TestCalculateDemo:
    def test_calc_demo():
        """
        Ensure that calculate_demo properly calculates;
        the rate limiter does not return a 4xx, but instead
        waits until the rate limit has ended, preventing the
        need for a further test
        """

        response = client.post(
            "/us/calculate",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer "
                + os.getenv("AUTH0_TEST_TOKEN_NO_DOMAIN"),
            },
            data=open(
                "./tests/python/data/calculate_us_1_data.json",
                "r",
                encoding="utf-8",
            ),
        )
        assert response.status_code == 200, response.text
