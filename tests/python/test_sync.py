import requests
import json
import sys

from tests.python.utils import client, extract_json_from_file

API_URL = "https://api.policyengine.org/"


def test_calculate_sync(client):
    """Confirm that the calculate endpoint outputs the same data as the main API"""

    country_id = "us"

    # Load the sample data
    input_data = extract_json_from_file(
        "./tests/python/data/calculate_us_1_data.json"
    )

    # Make a POST request to the API and store its output
    resAPI = requests.post(
        API_URL + "/" + country_id + "/calculate", json=input_data
    ).json()

    # Mock a POST request to API-light
    resLight = client.post(
        "/" + country_id + "/calculate",
        headers={"Content-Type": "application/json"},
        json=input_data,
    ).get_json()

    # Compare the outputs
    assert resAPI == resLight


def test_calculate_full_sync(client):
    """Confirm that the calculate endpoint outputs the same data as the main API"""

    country_id = "us"

    # Load the sample data
    input_data = extract_json_from_file(
        "./tests/python/data/calculate_us_1_data.json"
    )

    # Make a POST request to the API and store its output
    resAPI = requests.post(
        API_URL + "/" + country_id + "/calculate-full", json=input_data
    ).json()

    # Mock a POST request to API-light
    resLight = client.post(
        "/" + country_id + "/calculate-full",
        headers={"Content-Type": "application/json"},
        json=input_data,
    ).get_json()

    with open("resAPI.json", "w+") as outfile:
        outfile.write(json.dumps(resAPI))

    with open("resLight.json", "w+") as outfile:
        outfile.write(json.dumps(resLight))

    # Compare the outputs
    assert resAPI == resLight
