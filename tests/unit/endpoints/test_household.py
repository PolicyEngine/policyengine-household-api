import json
from unittest.mock import patch

import pytest
from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_api.endpoints.household import _validate_axes
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

    def test__given_ai_explainer_tracer_fails__returns_500(self, client):
        with patch(
            "policyengine_household_api.country.generate_computation_tree",
            side_effect=RuntimeError("tracer down"),
        ):
            response = client.post(
                "/us/calculate",
                json={
                    "household": valid_household_requesting_ctc_calculation,
                    "enable_ai_explainer": True,
                },
                headers=self.auth_headers,
            )

        assert response.status_code == 500
        payload = json.loads(response.data)
        assert payload["status"] == "error"
        assert "tracer down" in payload["message"]


class TestAxesValidation:
    @pytest.mark.parametrize(
        "household,message",
        [
            ({"axes": "not a list"}, "'axes' must be a list"),
            ({"axes": ["not an object"]}, "'axes[0]' must be an object"),
            (
                {"axes": [{"name": "employment_income", "count": "many"}]},
                "'axes[0].count' must be an integer",
            ),
            (
                {"axes": [{"name": "employment_income", "count": 0}]},
                "'axes[0].count' must be between 1 and 100",
            ),
            (
                {"axes": [{"name": "employment_income", "count": -1}]},
                "'axes[0].count' must be between 1 and 100",
            ),
        ],
    )
    def test__given_invalid_axes__raises_value_error(self, household, message):
        with pytest.raises(ValueError) as error:
            _validate_axes(household)

        assert message in str(error.value)

    @pytest.mark.parametrize(
        "household",
        [
            {},
            {"axes": []},
            {"axes": [{"name": "employment_income"}]},
            {"axes": [{"name": "employment_income", "count": "2"}]},
            {
                "axes": [
                    [
                        {"name": "employment_income", "count": 2},
                        {"name": "age"},
                    ]
                ]
            },
        ],
    )
    def test__given_valid_axes__does_not_raise(self, household):
        _validate_axes(household)
