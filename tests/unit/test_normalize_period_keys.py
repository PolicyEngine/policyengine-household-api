"""Unit tests for the YEAR-key → 12-monthly-keys normalization.

The normalization is what makes the household API behave like the hosted v1
API (api.policyengine.org) when partners send a YEAR-period key on a
MONTH-defined variable. See issue #1489.
"""

import pytest
from policyengine_us import CountryTaxBenefitSystem

from policyengine_household_api.country import (
    PolicyEngineCountry,
    _expand_year_keys_in_place,
    _normalize_period_keys,
)
from tests.fixtures.country import country_id_us, country_package_name_us


@pytest.fixture(scope="module")
def us_system():
    return CountryTaxBenefitSystem()


class TestExpandYearKeysInPlace:
    def test__numeric_annual_key__splits_into_twelve_months(self):
        # Given a numeric value keyed annually
        period_map = {"2026": 36000}

        # When the helper expands it in place
        _expand_year_keys_in_place(period_map)

        # Then the YEAR key is gone and 12 monthly keys carry value/12
        assert "2026" not in period_map
        for month in range(1, 13):
            assert period_map[f"2026-{month:02d}"] == 3000

    def test__float_annual_key__splits_with_float_division(self):
        period_map = {"2026": 31932}

        _expand_year_keys_in_place(period_map)

        for month in range(1, 13):
            assert period_map[f"2026-{month:02d}"] == 2661.0

    def test__boolean_annual_key__broadcasts_unchanged(self):
        period_map = {"2026": True}

        _expand_year_keys_in_place(period_map)

        assert "2026" not in period_map
        for month in range(1, 13):
            assert period_map[f"2026-{month:02d}"] is True

    def test__string_annual_key__broadcasts_unchanged(self):
        period_map = {"2026": "WA"}

        _expand_year_keys_in_place(period_map)

        for month in range(1, 13):
            assert period_map[f"2026-{month:02d}"] == "WA"

    def test__null_annual_key__leaves_year_key_intact(self):
        # Output requests must keep their YEAR key so the engine sums months.
        period_map = {"2026": None}

        _expand_year_keys_in_place(period_map)

        assert period_map == {"2026": None}

    def test__monthly_key__is_not_touched(self):
        period_map = {"2026-01": 3000}

        _expand_year_keys_in_place(period_map)

        assert period_map == {"2026-01": 3000}

    def test__mixed_annual_and_monthly__expands_only_annual(self):
        period_map = {"2026": 1200, "2027-03": 500}

        _expand_year_keys_in_place(period_map)

        assert "2026" not in period_map
        for month in range(1, 13):
            assert period_map[f"2026-{month:02d}"] == 100
        # The pre-existing monthly entry survives untouched.
        assert period_map["2027-03"] == 500

    def test__existing_monthly_key_is_preserved(self):
        # If a monthly key already exists, the spread must not overwrite it.
        period_map = {"2026": 1200, "2026-06": 999}

        _expand_year_keys_in_place(period_map)

        assert period_map["2026-06"] == 999
        # Other months get value/12.
        assert period_map["2026-01"] == 100


class TestNormalizePeriodKeys:
    def test__month_defined_variable__gets_split(self, us_system):
        # snap_earned_income is a MONTH-defined float in policyengine_us.
        household = {
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"2026": 31932}}
            },
        }

        _normalize_period_keys(household, us_system)

        snap_map = household["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert "2026" not in snap_map
        for month in range(1, 13):
            assert snap_map[f"2026-{month:02d}"] == 2661.0

    def test__year_defined_variable__is_left_alone(self, us_system):
        # employment_income is YEAR-defined — annual key is already correct.
        household = {
            "people": {"person_1": {"employment_income": {"2026": 31932}}},
        }

        _normalize_period_keys(household, us_system)

        emp = household["people"]["person_1"]["employment_income"]
        assert emp == {"2026": 31932}

    def test__year_defined_enum__is_left_alone(self, us_system):
        # state_name is YEAR-defined Enum — annual key is already correct.
        household = {
            "households": {"household_1": {"state_name": {"2026": "WA"}}},
        }

        _normalize_period_keys(household, us_system)

        assert household["households"]["household_1"]["state_name"] == {
            "2026": "WA"
        }

    def test__unknown_variable__is_left_alone(self, us_system):
        # Unrecognized variable names must not blow up the normalizer.
        household = {
            "spm_units": {
                "spm_unit_1": {"not_a_real_variable": {"2026": 999}}
            },
        }

        _normalize_period_keys(household, us_system)

        assert household["spm_units"]["spm_unit_1"]["not_a_real_variable"] == {
            "2026": 999
        }

    def test__axes_key__is_skipped(self, us_system):
        # `axes` is a list — it must not be misread as an entity-plural map.
        household = {
            "axes": [{"name": "employment_income", "count": 5}],
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"2026": 1200}}
            },
        }

        _normalize_period_keys(household, us_system)

        # The list is untouched.
        assert household["axes"] == [{"name": "employment_income", "count": 5}]
        # The MONTH var is still expanded.
        snap_map = household["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert snap_map["2026-06"] == 100

    def test__null_output_request__is_left_intact(self, us_system):
        # A `null` output request keyed annually keeps the YEAR key so the
        # engine returns the annual sum of the 12 monthly values.
        household = {
            "spm_units": {"spm_unit_1": {"snap": {"2026": None}}},
        }

        _normalize_period_keys(household, us_system)

        assert household["spm_units"]["spm_unit_1"]["snap"] == {"2026": None}

    def test__month_defined_boolean__broadcasts_true_unchanged(
        self, us_system
    ):
        # `is_incarcerated` is a MONTH-defined bool. A YEAR-keyed `True` must
        # broadcast to True for every month — it must NOT be coerced to
        # `True / 12 == 0.0833...` (bool is a subclass of int in Python).
        household = {
            "people": {"person_1": {"is_incarcerated": {"2026": True}}},
        }

        _normalize_period_keys(household, us_system)

        flag_map = household["people"]["person_1"]["is_incarcerated"]
        assert "2026" not in flag_map
        for month in range(1, 13):
            assert flag_map[f"2026-{month:02d}"] is True

    def test__month_defined_boolean__broadcasts_false_unchanged(
        self, us_system
    ):
        household = {
            "people": {"person_1": {"is_incarcerated": {"2026": False}}},
        }

        _normalize_period_keys(household, us_system)

        flag_map = household["people"]["person_1"]["is_incarcerated"]
        for month in range(1, 13):
            assert flag_map[f"2026-{month:02d}"] is False

    def test__month_defined_enum__broadcasts_unchanged(self, us_system):
        # `snap_utility_allowance_type` is a MONTH-defined Enum.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_utility_allowance_type": {"2026": "SUA"},
                }
            },
        }

        _normalize_period_keys(household, us_system)

        utility_map = household["spm_units"]["spm_unit_1"][
            "snap_utility_allowance_type"
        ]
        assert "2026" not in utility_map
        for month in range(1, 13):
            assert utility_map[f"2026-{month:02d}"] == "SUA"


def _wa_household(income_key, income_value, output_key):
    """Build a single-person WA SNAP household with a configurable input/output."""
    return {
        "people": {
            "person_1": {
                "age": {"2026": 34},
                "rent": {"2026": 10800},
            }
        },
        "tax_units": {"tax_unit_1": {"members": ["person_1"]}},
        "spm_units": {
            "spm_unit_1": {
                "members": ["person_1"],
                "snap": {output_key: None},
                "snap_gross_income": {income_key: income_value},
                "snap_assets": {"2026": 0},
            }
        },
        "households": {
            "household_1": {
                "members": ["person_1"],
                "state_name": {"2026": "WA"},
            }
        },
        "families": {"family_1": {"members": ["person_1"]}},
        "marital_units": {"marital_unit_1": {"members": ["person_1"]}},
    }


# Cross-product: 4 input variants × 2 output variants. Expected values are
# the v1 hosted-API responses on 2026-04-29; the post-fix household API must
# return identical numbers.
_SNAP_MATRIX = [
    # (case, income_key, income_value, output_key, expected_snap)
    ("A-O1", "2026", 36000, "2026", {"2026": 0.0}),
    ("A-O2", "2026", 36000, "2026-01", {"2026-01": 0.0}),
    ("B-O1", "2026", 3600, "2026", {"2026": 3596.0398}),
    ("B-O2", "2026", 3600, "2026-01", {"2026-01": 298.0}),
    ("C-O1", "2026-01", 36000, "2026", {"2026": 3298.0398}),
    ("C-O2", "2026-01", 36000, "2026-01", {"2026-01": 0.0}),
    ("D-O1", "2026-01", 3600, "2026", {"2026": 3298.0398}),
    ("D-O2", "2026-01", 3600, "2026-01", {"2026-01": 0.0}),
]


@pytest.fixture(scope="module")
def us_country():
    return PolicyEngineCountry(country_package_name_us, country_id_us)


class TestSnapInputOutputMatrix:
    """End-to-end: each row matches the hosted v1 API on api.policyengine.org.

    Documents the input/output contract partners can rely on:
    - YEAR-keyed numeric input on a MONTH-defined variable is split V/12 per month;
    - MONTH-keyed input applies to that one month only (others read the engine default);
    - YEAR-keyed output is the engine's sum across the 12 months;
    - MONTH-keyed output is the value for that single month.
    """

    @pytest.mark.parametrize(
        "income_key,income_value,output_key,expected_snap",
        [row[1:] for row in _SNAP_MATRIX],
        ids=[row[0] for row in _SNAP_MATRIX],
    )
    def test__matches_v1_api_behavior(
        self,
        us_country,
        income_key,
        income_value,
        output_key,
        expected_snap,
    ):
        household = _wa_household(income_key, income_value, output_key)

        result, _ = us_country.calculate(
            household=household,
            reform=None,
            enable_ai_explainer=False,
        )

        snap = result["spm_units"]["spm_unit_1"]["snap"]
        # Compare with float tolerance — engine values can carry small noise.
        assert snap.keys() == expected_snap.keys()
        for k in snap:
            assert snap[k] == pytest.approx(expected_snap[k], abs=0.01)

    def test__user_input_keys_are_echoed_unchanged(self, us_country):
        # Partners send `{"2026": V}` and must get `{"2026": V}` back even
        # though the engine internally sees the 12-month split.
        household = _wa_household("2026", 31932, "2026")

        result, _ = us_country.calculate(
            household=household,
            reform=None,
            enable_ai_explainer=False,
        )

        echoed = result["spm_units"]["spm_unit_1"]["snap_gross_income"]
        assert echoed == {"2026": 31932}
