import os
import requests
import json
import sys
from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_common.config_loader import get_config_value
from tests.to_refactor.fixtures import client, extract_json_from_file

API_URL = "https://api.policyengine.org/"


def _collapse_axis_expanded_inputs(node):
    """Collapse constant lists back to the scalar they repeat.

    Since policyengine-api #3825 the main API expands every request-supplied
    household value across the configured axes, so an input sent as ``40``
    comes back as ``[40.0] * count``. The household API echoes inputs as sent.
    Collapsing constant lists on both bodies lets the comparison cover the
    content of each response rather than that echo format.
    """
    if isinstance(node, dict):
        return {k: _collapse_axis_expanded_inputs(v) for k, v in node.items()}
    if isinstance(node, list):
        if node and all(not isinstance(x, (dict, list)) for x in node):
            if len(set(node)) == 1:
                return node[0]
            return node
        return [_collapse_axis_expanded_inputs(x) for x in node]
    return node


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

    policyengine_bundle = resLight.pop("policyengine_bundle")

    # The household API echoes inputs exactly as sent, even under axes.
    assert resLight["result"]["people"]["you"]["age"]["2023"] == 40

    # Compare the legacy response body, tolerating the main API's axis
    # expansion of request-supplied inputs, and assert the new provenance
    # separately.
    assert _collapse_axis_expanded_inputs(
        resAPI
    ) == _collapse_axis_expanded_inputs(resLight)
    assert policyengine_bundle == {
        "model_version": COUNTRY_PACKAGE_VERSIONS[country_id],
        "data_version": None,
        "dataset": None,
    }
