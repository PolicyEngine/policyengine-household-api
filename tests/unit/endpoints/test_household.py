import json

import pytest
from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from policyengine_household_api.endpoints.household import _validate_axes
from policyengine_household_api.modal_release.routing_metadata import (
    REQUESTED_VERSION_ENVIRON_KEY,
    RESOLVED_CHANNEL_ENVIRON_KEY,
)
from policyengine_household_api.utils.config_loader import get_config_value
from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
)


class TestCalculateEndpoint:
    auth_headers = {
        "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
    }

    uk_single_adult_household = {
        "people": {
            "person": {
                "age": {"2026": 30},
                "employment_income": {"2026": 30_000},
                "income_tax": {"2026": None},
            }
        },
        "benunits": {
            "benunit": {
                "members": ["person"],
            }
        },
        "households": {
            "household": {
                "members": ["person"],
                "household_net_income": {"2026": None},
            }
        },
    }

    @pytest.mark.parametrize(
        "country_id,household,result_path,expected_value",
        [
            (
                "ca",
                {
                    "people": {
                        "person": {
                            "age": {"2026": 40},
                            "employment_income": {"2026": 50_000},
                            "climate_action_incentive_category": {
                                "2026": "HEAD"
                            },
                            "individual_net_income": {"2026": None},
                        }
                    },
                    "households": {
                        "household": {
                            "members": ["person"],
                            "province": {"2026": "ONTARIO"},
                            "household_net_income": {"2026": None},
                        }
                    },
                },
                (
                    "households",
                    "household",
                    "household_net_income",
                    "2026",
                ),
                47_693.266,
            ),
            (
                "ng",
                {
                    "people": {
                        "person": {
                            "age": {"2026": 40},
                            "employment_income": {"2026": 5_000_000},
                            "tax": {"2026": None},
                        }
                    },
                    "households": {
                        "household": {
                            "members": ["person"],
                            "household_net_income": {"2026": None},
                        }
                    },
                },
                ("people", "person", "tax", "2026"),
                704_000.0,
            ),
            (
                "il",
                {
                    "people": {
                        "person": {
                            "age": {"2026": 40},
                            "employment_income": {"2026": 200_000},
                            "tax": {"2026": None},
                        }
                    },
                    "households": {
                        "household": {
                            "members": ["person"],
                            "household_net_income": {"2026": None},
                        }
                    },
                },
                ("people", "person", "tax", "2026"),
                4_800.0,
            ),
        ],
    )
    def test__additional_supported_countries_calculate(
        self, client, country_id, household, result_path, expected_value
    ):
        response = client.post(
            f"/{country_id}/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 200
        payload = json.loads(response.data)
        assert payload["status"] == "ok"
        assert payload["policyengine_bundle"] == {
            "model_version": COUNTRY_PACKAGE_VERSIONS[country_id],
            "data_version": None,
            "dataset": None,
        }

        result_value = payload["result"]
        for key in result_path:
            result_value = result_value[key]
        assert result_value == pytest.approx(expected_value)

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

    def test__uk_calculate_returns_requested_results(self, client):
        response = client.post(
            "/uk/calculate",
            json={"household": self.uk_single_adult_household},
            headers=self.auth_headers,
        )

        assert response.status_code == 200
        payload = json.loads(response.data)
        assert payload["status"] == "ok"
        assert payload["result"]["people"]["person"]["income_tax"]["2026"] == (
            pytest.approx(3486.0)
        )
        assert payload["result"]["households"]["household"][
            "household_net_income"
        ]["2026"] == pytest.approx(24960.55)
        assert payload["policyengine_bundle"] == {
            "model_version": COUNTRY_PACKAGE_VERSIONS["uk"],
            "data_version": None,
            "dataset": None,
        }

    def test__uk_calculate_applies_policy_reform(self, client):
        response = client.post(
            "/uk/calculate",
            json={
                "household": self.uk_single_adult_household,
                "policy": {
                    "gov.hmrc.income_tax.allowances.personal_allowance.amount": {
                        "2026-01-01.2100-12-31": 15_000,
                    }
                },
            },
            headers=self.auth_headers,
        )

        assert response.status_code == 200
        payload = json.loads(response.data)
        assert payload["status"] == "ok"
        assert payload["result"]["people"]["person"]["income_tax"]["2026"] == (
            pytest.approx(3000.0)
        )
        assert payload["result"]["households"]["household"][
            "household_net_income"
        ]["2026"] == pytest.approx(25446.55)

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
                    "age": {"2026": 40},
                    "medical_out_of_pocket_expenses": {"2026": 0},
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
            payload["result"]["tax_units"]["tax_unit"]["ctc"]["2026"]
            is not None
        )
        # The deprecation warning is surfaced in the response.
        assert "warnings" in payload
        assert any(
            "medical_out_of_pocket_expenses" in w and "deprecated" in w.lower()
            for w in payload["warnings"]
        )

    def test__deprecated_axis_name__is_dropped_with_warning(self, client):
        household = {
            **valid_household_requesting_ctc_calculation,
            "axes": [
                [
                    {
                        "name": "medical_out_of_pocket_expenses",
                        "period": "2026",
                        "min": 0,
                        "max": 1000,
                        "count": 2,
                    }
                ]
            ],
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 200
        payload = json.loads(response.data)
        assert payload["status"] == "ok"
        assert (
            payload["result"]["tax_units"]["tax_unit"]["ctc"]["2026"]
            is not None
        )
        assert any(
            "medical_out_of_pocket_expenses" in w and "axes[0][0].name" in w
            for w in payload["warnings"]
        )

    def test__unknown_input_variable__returns_400_with_errors(self, client):
        household = {
            **valid_household_requesting_ctc_calculation,
            "people": {
                "you": {
                    "age": {"2026": 40},
                    "definitely_not_a_variable": {"2026": 0},
                }
            },
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 400
        payload = json.loads(response.data)
        assert payload["status"] == "error"
        assert payload["message"] == "Invalid household variables."
        assert "errors" in payload
        assert any(
            "Variable `definitely_not_a_variable`" in error
            and "PolicyEngine model version" in error
            for error in payload["errors"]
        )

    def test__analytics_enabled__captures_unknown_variable_before_400(
        self, client, calculate_analytics_capture
    ):
        household = {
            **valid_household_requesting_ctc_calculation,
            "people": {
                "you": {
                    "age": {"2026": 40},
                    "definitely_not_a_variable": {"2026": 0},
                }
            },
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 400
        calculate_request = calculate_analytics_capture.calculate_request
        unknown_variable = calculate_analytics_capture.variable_row(
            "definitely_not_a_variable"
        )

        assert calculate_request.client_id == "test-client"
        assert calculate_request.visit_id is not None
        assert calculate_request.country_id == "us"
        assert calculate_request.response_status_code == 400
        assert calculate_request.unsupported_variable_count == 1
        assert unknown_variable.availability_status == "unsupported"
        assert unknown_variable.entity_type == "person"
        assert unknown_variable.source == "household_input"
        assert unknown_variable.period_granularity == "year"
        calculate_analytics_capture.db.session.commit.assert_called_once()

    def test__analytics_enabled__captures_modal_routing_metadata(
        self, client, calculate_analytics_capture
    ):
        response = client.post(
            "/us/calculate",
            json={"household": valid_household_requesting_ctc_calculation},
            headers=self.auth_headers,
            environ_overrides={
                REQUESTED_VERSION_ENVIRON_KEY: "1.691.1",
                RESOLVED_CHANNEL_ENVIRON_KEY: "frontier",
            },
        )

        assert response.status_code == 200
        calculate_request = calculate_analytics_capture.calculate_request
        assert calculate_request.requested_version == "1.691.1"
        assert calculate_request.resolved_channel == "frontier"
        assert {
            variable.requested_version
            for variable in calculate_analytics_capture.variable_rows
        } == {"1.691.1"}
        assert {
            variable.resolved_channel
            for variable in calculate_analytics_capture.variable_rows
        } == {"frontier"}

    def test__analytics_enabled__ignores_spoofed_modal_routing_headers(
        self, client, calculate_analytics_capture
    ):
        response = client.post(
            "/us/calculate",
            json={"household": valid_household_requesting_ctc_calculation},
            headers={
                **self.auth_headers,
                "X-PolicyEngine-Requested-Version": "frontier",
                "X-PolicyEngine-Resolved-Channel": "frontier",
            },
        )

        assert response.status_code == 200
        calculate_request = calculate_analytics_capture.calculate_request
        assert calculate_request.requested_version is None
        assert calculate_request.resolved_channel is None

    def test__unknown_axis_variable__returns_400_with_errors(self, client):
        household = {
            **valid_household_requesting_ctc_calculation,
            "axes": [{"name": "definitely_not_a_variable", "count": 2}],
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 400
        payload = json.loads(response.data)
        assert payload["status"] == "error"
        assert any(
            "Variable `definitely_not_a_variable`" in error
            and "axes[0].name" in error
            for error in payload["errors"]
        )

    def test__given_invalid_axis_name_type__returns_400(self, client):
        household = {
            **valid_household_requesting_ctc_calculation,
            "axes": [{"name": ["not", "a", "string"], "count": 2}],
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 400
        payload = json.loads(response.data)
        assert payload["status"] == "error"
        assert (
            "'axes[0].name' must be a non-empty string" in payload["message"]
        )

    def test__analytics_enabled__truncates_overlong_variable_names(
        self, client, calculate_analytics_capture
    ):
        long_variable_name = "very_long_" + ("x" * 251)
        household = {
            **valid_household_requesting_ctc_calculation,
            "people": {
                "you": {
                    "age": {"2026": 40},
                    long_variable_name: {"2026": 0},
                }
            },
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 400
        truncated_row = next(
            row
            for row in calculate_analytics_capture.variable_rows
            if row.variable_name_truncated
        )
        assert truncated_row.variable_name == long_variable_name[:250] + "..."
        assert len(truncated_row.variable_name) == 253
        assert truncated_row.availability_status == "unsupported"

    def test__analytics_enabled__keeps_duplicate_truncated_variable_rows(
        self, client, calculate_analytics_capture
    ):
        shared_prefix = "x" * 250
        first_variable_name = shared_prefix + "a"
        second_variable_name = shared_prefix + "b"
        household = {
            **valid_household_requesting_ctc_calculation,
            "people": {
                "you": {
                    "age": {"2026": 40},
                    first_variable_name: {"2026": 0},
                    second_variable_name: {"2026": 1},
                }
            },
        }

        response = client.post(
            "/us/calculate",
            json={"household": household},
            headers=self.auth_headers,
        )

        assert response.status_code == 400
        truncated_rows = [
            row
            for row in calculate_analytics_capture.variable_rows
            if row.variable_name_truncated
        ]
        assert len(truncated_rows) == 2
        assert {row.variable_name for row in truncated_rows} == {
            shared_prefix + "..."
        }
        assert all(
            row.availability_status == "unsupported" for row in truncated_rows
        )
        assert (
            calculate_analytics_capture.calculate_request.unsupported_variable_count
            == 2
        )

    def test__extraneous_request_key_is_ignored(self, client):
        response = client.post(
            "/us/calculate",
            json={
                "household": valid_household_requesting_ctc_calculation,
                "extraneous_key": True,
            },
            headers=self.auth_headers,
        )

        assert response.status_code == 200
        payload = json.loads(response.data)
        assert payload["status"] == "ok"


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
                {"axes": [{"name": ["employment_income"], "count": 2}]},
                "'axes[0].name' must be a non-empty string",
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
