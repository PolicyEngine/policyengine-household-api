import os
from dotenv import load_dotenv

from tests.python.utils import client

load_dotenv()


def test_calculate_liveness(client):
    """This tests that, when passed relevant data, calculate endpoint returns something"""
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
