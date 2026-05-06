import pytest
from policyengine_us import CountryTaxBenefitSystem

from policyengine_household_api.utils.variable_validation import (
    HouseholdVariableValidationError,
    validate_household_variables,
)


@pytest.fixture(scope="module")
def us_system():
    return CountryTaxBenefitSystem()


class TestValidateHouseholdVariables:
    def test__known_variables__return_no_errors(self, us_system):
        household = {
            "people": {
                "you": {
                    "age": {"2026": 40},
                    "employment_income": {"2026": 50_000},
                }
            },
            "households": {
                "household": {
                    "members": ["you"],
                    "state_code_str": {"2026": "CA"},
                }
            },
        }

        errors = validate_household_variables(
            household, us_system, model_version="1.687.0"
        )

        assert errors == []

    def test__deprecated_allowlisted_variable__returns_no_errors(
        self, us_system
    ):
        household = {
            "people": {
                "you": {
                    "medical_out_of_pocket_expenses": {"2026": 100},
                }
            }
        }

        errors = validate_household_variables(
            household, us_system, model_version="1.687.0"
        )

        assert errors == []

    def test__unknown_variable__returns_error(self, us_system):
        household = {
            "people": {
                "you": {
                    "definitely_not_a_variable": {"2026": 100},
                }
            }
        }

        errors = validate_household_variables(
            household, us_system, model_version="1.687.0"
        )

        assert len(errors) == 1
        assert isinstance(errors[0], HouseholdVariableValidationError)
        assert errors[0].variable == "definitely_not_a_variable"
        assert errors[0].entity_plural == "people"
        assert errors[0].entity_id == "you"
        assert "Variable `definitely_not_a_variable`" in errors[0].message
        assert "people/you" in errors[0].message
        assert "1.687.0" in errors[0].message

    def test__members_list__is_not_treated_as_variable(self, us_system):
        household = {
            "spm_units": {
                "spm_unit": {
                    "members": ["you"],
                    "snap": {"2026": None},
                }
            }
        }

        errors = validate_household_variables(
            household, us_system, model_version="1.687.0"
        )

        assert errors == []

    def test__unknown_axis_name__returns_error(self, us_system):
        household = {
            "people": {"you": {"age": {"2026": 40}}},
            "axes": [
                [
                    {
                        "name": "not_available_on_this_model",
                        "period": "2026",
                        "min": 0,
                        "max": 100,
                        "count": 2,
                    }
                ]
            ],
        }

        errors = validate_household_variables(
            household, us_system, model_version="1.687.0"
        )

        assert len(errors) == 1
        assert errors[0].variable == "not_available_on_this_model"
        assert "axes[0][0].name" in errors[0].message

    def test__deprecated_axis_name__returns_no_errors(self, us_system):
        household = {
            "people": {"you": {"age": {"2026": 40}}},
            "axes": [{"name": "medical_out_of_pocket_expenses"}],
        }

        errors = validate_household_variables(
            household, us_system, model_version="1.687.0"
        )

        assert errors == []
