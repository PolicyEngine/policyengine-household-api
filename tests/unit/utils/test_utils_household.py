"""Unit tests for utils/household.py (flatten_variables_from_household)."""

import pytest

from policyengine_household_api.models.household import HouseholdModelUS
from policyengine_household_api.utils.household import (
    flatten_variables_from_household,
    FlattenedVariable,
    FlattenedVariableFilter,
)


def _build_household(periods: dict) -> HouseholdModelUS:
    """Build a minimal HouseholdModelUS where one variable has multiple periods."""
    return HouseholdModelUS.model_validate(
        {
            "people": {
                "you": {
                    "employment_income": periods,
                }
            },
            "households": {
                "your household": {"members": ["you"]},
            },
        }
    )


class TestFlattenVariablesFromHousehold:
    """Ensure we flatten every (entity, variable, period) tuple."""

    def test__given_three_periods__three_entries_returned(self):
        household = _build_household(
            {"2026": 1000, "2027": 2000, "2028": 3000}
        )

        flattened = flatten_variables_from_household(household)

        employment_income = [
            v for v in flattened if v.variable == "employment_income"
        ]
        assert len(employment_income) == 3
        periods = {v.period for v in employment_income}
        assert periods == {"2026", "2027", "2028"}
        values = {v.period: v.value for v in employment_income}
        assert values == {"2026": 1000, "2027": 2000, "2028": 3000}

    def test__given_single_period__single_entry_returned(self):
        household = _build_household({"2026": 5000})

        flattened = flatten_variables_from_household(household)

        employment_income = [
            v for v in flattened if v.variable == "employment_income"
        ]
        assert len(employment_income) == 1
        assert employment_income[0].period == "2026"
        assert employment_income[0].value == 5000

    def test__given_variable_with_zero_periods__no_entries_and_no_error(
        self,
    ):
        """A variable whose period dict is empty must not leak the last
        loop binding from an earlier variable. Regression guard for the
        indentation-era bug where ``new_pair`` was referenced outside
        the period loop (``UnboundLocalError`` if no periods ever ran,
        or the previous variable's tuple reappearing here).
        """
        household = HouseholdModelUS.model_validate(
            {
                "people": {
                    "you": {
                        # Explicit zero-period dict.
                        "employment_income": {},
                    }
                },
                "households": {
                    "your household": {"members": ["you"]},
                },
            }
        )

        # Should not raise.
        flattened = flatten_variables_from_household(household)

        employment_income = [
            v for v in flattened if v.variable == "employment_income"
        ]
        assert employment_income == []

    def test__given_filter__only_matching_entries_returned(self):
        household = _build_household({"2026": 1, "2027": 2})

        flattened = flatten_variables_from_household(
            household,
            filter=FlattenedVariableFilter(
                filter_on="period", desired_value="2027"
            ),
        )

        employment_income = [
            v for v in flattened if v.variable == "employment_income"
        ]
        assert len(employment_income) == 1
        assert employment_income[0].period == "2027"
