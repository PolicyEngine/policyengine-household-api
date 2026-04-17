import json

from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_api.utils.config_loader import get_config_value
from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
)


class TestCalculateEndpoint:
    auth_headers = {
        "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
    }

    def test_returns_policyengine_bundle(self, client):
        response = client.post(
            "/us/calculate",
            json={"household": valid_household_requesting_ctc_calculation},
            headers=self.auth_headers,
        )

        assert response.status_code == 200

        payload = json.loads(response.data)
        assert payload["policyengine_bundle"] == {
            "model_version": COUNTRY_PACKAGE_VERSIONS["us"],
            "data_version": None,
            "dataset": None,
        }

    def test__given_invalid_household_shape__returns_400(self, client):
        response = client.post(
            "/us/calculate",
            json={"household": "not a dict"},
            headers=self.auth_headers,
        )
        assert response.status_code == 400
        payload = json.loads(response.data)
        assert payload["status"] == "error"

    def test__given_too_many_axes__returns_400(self, client):
        response = client.post(
            "/us/calculate",
            json={
                "household": {
                    **valid_household_requesting_ctc_calculation,
                    "axes": [[{"name": "employment_income", "count": 5}]] * 11,
                }
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 400

    def test__given_axes_count_over_cap__returns_400(self, client):
        response = client.post(
            "/us/calculate",
            json={
                "household": {
                    **valid_household_requesting_ctc_calculation,
                    "axes": [[{"name": "employment_income", "count": 500}]],
                }
            },
            headers=self.auth_headers,
        )
        assert response.status_code == 400
