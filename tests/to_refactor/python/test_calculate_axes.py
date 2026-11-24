from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_common.config_loader import get_config_value
from tests.to_refactor.fixtures import client, extract_json_from_file


def test_calculate_echoes_inputs_under_axes(client):
    """Confirm that an axes request echoes its inputs and reports the bundle.

    This test once compared the response body with the main API's
    (api.policyengine.org). The sample request asks for no outputs, so that
    comparison covered only the input echo, and the main API now serves only
    authenticated PolicyEngine servers. The test keeps the household API's own
    assertions.
    """

    country_id = "us"

    # Load the sample data
    input_data = extract_json_from_file(
        "./tests/to_refactor/python/data/calculate_us_1_data.json"
    )

    response = client.post(
        "/" + country_id + "/calculate",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
        },
        json=input_data,
    )
    assert response.status_code == 200, response.text
    body = response.get_json()

    # The household API echoes inputs exactly as sent, even under axes.
    assert body["result"]["people"]["you"]["age"]["2023"] == 40
    assert body["policyengine_bundle"] == {
        "model_version": COUNTRY_PACKAGE_VERSIONS[country_id],
        "data_version": None,
        "dataset": None,
    }
