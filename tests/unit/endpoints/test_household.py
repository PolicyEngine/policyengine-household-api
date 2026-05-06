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

    def test__year_keyed_input_reaches_engine(self, client):
        """Regression guard for the silent-drop bug fixed in PR #1490.

        Year-keyed numeric input on a MONTH-defined variable used to be
        silently dropped, so partner inputs read as 0 inside the engine.
        Asserts that a non-zero year-keyed input produces a different
        annual result from a zero year-keyed input — independent of which
        program rules are in force, so it survives parameter updates.
        """

        def snap_with(employment_income: int) -> float:
            household = {
                "people": {
                    "parent_1": {
                        "age": {"2026": 35},
                        "employment_income": {"2026": employment_income},
                    },
                    "parent_2": {"age": {"2026": 35}},
                    "child_1": {"age": {"2026": 7}},
                    "child_2": {"age": {"2026": 4}},
                },
                "families": {
                    "family_1": {
                        "members": [
                            "parent_1",
                            "parent_2",
                            "child_1",
                            "child_2",
                        ]
                    }
                },
                "tax_units": {
                    "tax_unit_1": {
                        "members": [
                            "parent_1",
                            "parent_2",
                            "child_1",
                            "child_2",
                        ]
                    }
                },
                "households": {
                    "household_1": {
                        "members": [
                            "parent_1",
                            "parent_2",
                            "child_1",
                            "child_2",
                        ],
                        "state_name": {"2026": "CA"},
                    }
                },
                "spm_units": {
                    "spm_unit_1": {
                        "members": [
                            "parent_1",
                            "parent_2",
                            "child_1",
                            "child_2",
                        ],
                        "snap": {"2026": None},
                    }
                },
            }
            response = client.post(
                "/us/calculate",
                json={"household": household},
                headers=self.auth_headers,
            )
            assert response.status_code == 200
            payload = json.loads(response.data)
            return payload["result"]["spm_units"]["spm_unit_1"]["snap"]["2026"]

        snap_with_earnings = snap_with(30_000)
        snap_without_earnings = snap_with(0)

        assert snap_without_earnings != snap_with_earnings, (
            "SNAP did not respond to year-keyed employment_income — "
            "the year-to-month distribution was likely dropped before "
            "reaching the engine."
        )

    def test__deprecated_input__is_dropped_with_warning(self, client):
        """A removed model variable in the payload must not crash the request.

        `medical_out_of_pocket_expenses` was removed from policyengine-us in
        1.673.0. Without warn-and-drop, partner traffic carrying it raises
        `VariableNotFoundError` → HTTP 500 and the partner sees no output
        at all. With warn-and-drop, the field is stripped before the engine
        sees it and a structured warning is appended to the response.
        """
        household = {
            **valid_household_requesting_ctc_calculation,
            "people": {
                "you": {
                    "age": {"2024": 40},
                    "medical_out_of_pocket_expenses": {"2024": 0},
                }
            },
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 200
        payload = json.loads(response.data)
        assert payload["status"] == "ok"
        # CTC still computes — non-medical outputs are unaffected.
        assert (
            payload["result"]["tax_units"]["tax_unit"]["ctc"]["2024"]
            is not None
        )
        # The deprecation warning is surfaced in the response.
        assert "warnings" in payload
        assert any(
            "medical_out_of_pocket_expenses" in w and "deprecated" in w.lower()
            for w in payload["warnings"]
        )

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
