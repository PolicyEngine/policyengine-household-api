import os
import requests
import json
import sys
from policyengine_household_api.utils.config_loader import get_config_value
from tests.to_refactor.fixtures import client, extract_json_from_file

API_URL = "https://api.policyengine.org/"


def test_calculate_sync(client):
    """Confirm that the calculate endpoint outputs the same data as the main API"""

    country_id = "us"

    # Load the sample data
    input_data = extract_json_from_file(
        "./tests/to_refactor/python/data/calculate_us_1_data.json"
    )

    # Make a POST request to the API and store its output
    resAPI = requests.post(
        API_URL + "/" + country_id + "/calculate", json=input_data
    ).json()

    # Mock a POST request to household-API
    resLight = client.post(
        "/" + country_id + "/calculate",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
        },
        json=input_data,
    ).get_json()

    # Compare the outputs
    assert resAPI == resLight
