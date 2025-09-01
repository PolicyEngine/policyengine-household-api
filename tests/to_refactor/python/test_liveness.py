import os

from policyengine_household_api.utils.config_loader import get_config_value
from tests.to_refactor.fixtures import client

def test_calculate_liveness(client):
    """This tests that, when passed relevant data, calculate endpoint returns something"""
    response = client.post(
        "/us/calculate",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
        },
        data=open(
            "./tests/to_refactor/python/data/calculate_us_1_data.json",
            "r",
            encoding="utf-8",
        ),
    )
    assert response.status_code == 200, response.text
