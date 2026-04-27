import json
from typing import Any

import pytest

from policyengine_household_api.models.household import HouseholdModelUS
from policyengine_household_api.utils.household import (
    FlattenedVariable,
    FlattenedVariableFilter,
    flatten_variables_from_household,
)
from tests.data.customer_households import (
    amplifi_household,
    amplifi_household_2025,
    impactica_household,
    my_friend_ben_household,
)


class TestCustomerInputs:
    @pytest.mark.parametrize(
        "household",
        [
            my_friend_ben_household,
        ],
    )
    def test_my_friend_ben(self, deployed_api, auth_token, household):
        self.us_household_runner(deployed_api, auth_token, household)

    @pytest.mark.parametrize(
        "household",
        [
            amplifi_household,
            amplifi_household_2025,
        ],
    )
    def test_amplifi(self, deployed_api, auth_token, household):
        self.us_household_runner(deployed_api, auth_token, household)

    @pytest.mark.parametrize(
        "household",
        [
            impactica_household,
        ],
    )
    def test_impactica(self, deployed_api, auth_token, household):
        self.us_household_runner(deployed_api, auth_token, household)

    def us_household_runner(self, deployed_api, auth_token, household):
        household_model = HouseholdModelUS(**household)
        variables_to_calc, input_variables = self._prepare_variables(
            household_model
        )
        response = deployed_api.post(
            "/us/calculate",
            headers={
                "Authorization": f"Bearer {auth_token}",
            },
            json_body={
                "household": household_model.model_dump(),
            },
        )

        self._verify_calculation_response(
            response, input_variables, variables_to_calc
        )

    def _prepare_variables(
        self, household: HouseholdModelUS
    ) -> tuple[list[FlattenedVariable], list[FlattenedVariable]]:
        calc_filter = FlattenedVariableFilter(
            filter_on="value", desired_value=None
        )
        input_filter = FlattenedVariableFilter(
            filter_on="value", desired_value=lambda value: value is not None
        )

        variables_to_calc = flatten_variables_from_household(
            household=household,
            filter=calc_filter,
        )
        input_variables = flatten_variables_from_household(
            household=household,
            filter=input_filter,
        )

        return variables_to_calc, input_variables

    def _verify_calculation_response(
        self, response, input_variables, variables_to_calc
    ):
        assert response.status_code == 200

        result = response.json()
        self._verify_response_schema(result)

        response_vars = self._extract_response_variables(result)
        self._verify_input_variables_unchanged(input_variables, response_vars)
        self._verify_calculated_variables_populated(
            variables_to_calc, response_vars
        )

    def _verify_response_schema(self, result: dict[str, Any]):
        assert result["status"] == "ok"
        assert result["message"] is None

    def _extract_response_variables(
        self, result: dict[str, Any]
    ) -> list[FlattenedVariable]:
        return flatten_variables_from_household(
            household=HouseholdModelUS(**result["result"]),
        )

    def _verify_input_variables_unchanged(
        self,
        input_variables: list[FlattenedVariable],
        response_vars: list[FlattenedVariable],
    ):
        response_var_dict = {var.variable: var for var in response_vars}

        for variable in input_variables:
            assert variable.variable in response_var_dict
            assert variable.value == response_var_dict[variable.variable].value

    def _verify_calculated_variables_populated(
        self,
        variables_to_calc: list[FlattenedVariable],
        response_vars: list[FlattenedVariable],
    ):
        response_var_dict = {var.variable: var for var in response_vars}

        for variable in variables_to_calc:
            assert variable.variable in response_var_dict
            assert response_var_dict[variable.variable].value is not None
