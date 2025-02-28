import pytest
import json
import os
from flask import Response
from typing import Any, List, Tuple
from tests.data.customer_households import my_friend_ben_household
from policyengine_household_api.models.household import HouseholdModelUS
from policyengine_household_api.utils.household import (
    FlattenedVariableFilter,
    FlattenedVariable,
    flatten_variables_from_household,
)


class TestCustomerInputs:

    @pytest.mark.parametrize(
        "household",
        [
            my_friend_ben_household,
        ],
    )
    def test_my_friend_ben(self, client, household):
        """
        Test that household calculations work correctly for 'my_friend_ben' test case.

        Given a household with some input values and some values to be calculated
        When the calculation API is called with this household
        Then all input values should remain unchanged and all calculated values should be populated
        """
        # Given
        household_model = HouseholdModelUS(**household)
        country_id = "us"
        variables_to_calc: list[FlattenedVariable]
        input_variables: list[FlattenedVariable]
        variables_to_calc, input_variables = self._prepare_variables(
            household_model
        )
        request: dict[str, Any] = self._create_calculation_request(
            household_model
        )

        # When
        response: Response = self._execute_calculation_request(
            client, country_id, request
        )

        # Then
        self._verify_calculation_response(
            response, input_variables, variables_to_calc
        )

    def _prepare_variables(
        self, household: HouseholdModelUS
    ) -> Tuple[list[FlattenedVariable], list[FlattenedVariable]]:
        """Extract variables to calculate and input variables from a household."""
        calc_filter = FlattenedVariableFilter(
            filter_on="value", desired_value=None
        )
        input_filter = FlattenedVariableFilter(
            filter_on="value", desired_value=lambda x: x is not None
        )

        variables_to_calc: list[FlattenedVariable] = (
            flatten_variables_from_household(
                household=household,
                filter=calc_filter,
            )
        )

        input_variables: list[FlattenedVariable] = (
            flatten_variables_from_household(
                household=household,
                filter=input_filter,
            )
        )

        return variables_to_calc, input_variables

    def _create_calculation_request(self, household: HouseholdModelUS) -> dict:
        household_dict = household.model_dump()
        """Create the request for a calculation."""
        return {
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('AUTH0_TEST_TOKEN_NO_DOMAIN')}",
            },
            "body": {
                "household": household_dict,
            },
        }

    def _execute_calculation_request(
        self, client, country_id, request
    ) -> Response:
        """Execute the calculation request against the API."""
        return client.post(
            f"/{country_id}/calculate",
            headers=request["headers"],
            json=request["body"],
        )

    def _verify_calculation_response(
        self, response, input_variables, variables_to_calc
    ):
        """Verify that the calculation response is correct."""
        assert response.status_code == 200

        result = json.loads(response.data)
        self._verify_response_schema(result)

        response_vars = self._extract_response_variables(result)
        self._verify_input_variables_unchanged(input_variables, response_vars)
        self._verify_calculated_variables_populated(
            variables_to_calc, response_vars
        )

    def _verify_response_schema(self, result):
        """Verify that the response follows the expected schema."""
        assert result["status"] == "ok"
        assert result["message"] is None

    def _extract_response_variables(self, result) -> List[FlattenedVariable]:
        """Extract the variables from the response."""
        return flatten_variables_from_household(
            household=HouseholdModelUS(**result["result"]),
        )

    def _verify_input_variables_unchanged(
        self, input_variables, response_vars
    ):
        """Verify that input variables remain unchanged in the response."""
        # E.g., {"eitc": FlattenedVariable("eitc", 1000), ...}
        response_var_dict = {var.variable: var for var in response_vars}

        for variable in input_variables:
            assert variable.variable in response_var_dict
            assert variable.value == response_var_dict[variable.variable].value

    def _verify_calculated_variables_populated(
        self, variables_to_calc, response_vars
    ):
        """Verify that calculated variables have been populated with values."""
        # E.g., {"eitc": FlattenedVariable("eitc", 1000), ...}
        response_var_dict = {var.variable: var for var in response_vars}

        for variable in variables_to_calc:
            assert variable.variable in response_var_dict
            assert response_var_dict[variable.variable].value is not None
