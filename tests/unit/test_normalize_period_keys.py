"""Tests for the YEAR-key -> 12-monthly-keys normalization.

The normalizer makes the household API behave like the hosted v1 API
(api.policyengine.org) when partners send a YEAR-period key on a
MONTH-defined variable. See issue #1489.

These tests drive the public-ish entry point ``_normalize_period_keys``
with real variables from the policyengine-us system so the value-type
branch (numeric vs. bool/str/enum) is exercised end-to-end.
"""

import pytest
from policyengine_us import CountryTaxBenefitSystem

from policyengine_household_api.country import (
    PolicyEngineCountry,
    _normalize_period_keys,
    validate_period_budgets,
)
from tests.fixtures.country import country_id_us, country_package_name_us


@pytest.fixture(scope="module")
def us_system():
    return CountryTaxBenefitSystem()


# ---------------------------------------------------------------------------
# _normalize_period_keys: numeric MONTH-defined variables
# ---------------------------------------------------------------------------


class TestNumericMonthDefinedVariable:
    """`snap_earned_income` is a MONTH-defined float in policyengine_us."""

    def test__year_only__splits_value_across_twelve_months(self, us_system):
        household = {
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"2026": 31932}}
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert "2026" not in snap_map
        for month in range(1, 13):
            assert snap_map[f"2026-{month:02d}"] == 2661.0

    def test__year_plus_partial_months__remainder_distributes_to_unset(
        self, us_system
    ):
        # Annual $1200 with explicit June=$600 → remainder $600 split over
        # the other 11 months as an unrounded float (matches v1 — see
        # /tmp/v1_breakdown probe). Engine consumes the float directly.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 1200, "2026-06": 600}
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert snap_map["2026-06"] == 600
        assert snap_map["2026-01"] == pytest.approx(600 / 11)
        assert snap_map["2026-12"] == pytest.approx(600 / 11)
        assert "2026" not in snap_map

    def test__year_plus_months_summing_to_year__unset_months_zero(
        self, us_system
    ):
        # Annual $600 with explicit Jan+Feb=$300+$300 → remainder $0 →
        # other 10 months get $0.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        "2026": 600,
                        "2026-01": 300,
                        "2026-02": 300,
                    }
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert snap_map["2026-01"] == 300
        assert snap_map["2026-02"] == 300
        for month in range(3, 13):
            assert snap_map[f"2026-{month:02d}"] == 0.0

    def test__year_plus_all_twelve_months__year_key_dropped(self, us_system):
        # All 12 months explicit and consistent with the annual total —
        # the YEAR key just disappears, every month keeps its explicit value.
        explicit = {f"2026-{m:02d}": 100 for m in range(1, 13)}
        explicit["2026"] = 1200
        household = {
            "spm_units": {"spm_unit_1": {"snap_earned_income": explicit}}
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert "2026" not in snap_map
        for month in range(1, 13):
            assert snap_map[f"2026-{month:02d}"] == 100

    def test__null_year_output__year_key_left_intact(self, us_system):
        # Output requests must keep the YEAR key so the engine sums the months.
        household = {"spm_units": {"spm_unit_1": {"snap": {"2026": None}}}}

        normalized = _normalize_period_keys(household, us_system)

        assert normalized["spm_units"]["spm_unit_1"]["snap"] == {"2026": None}

    def test__monthly_only__not_touched(self, us_system):
        household = {
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"2026-01": 3000}}
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        assert normalized["spm_units"]["spm_unit_1"]["snap_earned_income"] == {
            "2026-01": 3000
        }


# ---------------------------------------------------------------------------
# _normalize_period_keys: bool / enum / string MONTH-defined variables
# ---------------------------------------------------------------------------


class TestNonNumericMonthDefinedVariable:
    def test__boolean_year_key__broadcasts_true_unchanged(self, us_system):
        # `is_incarcerated` is a MONTH-defined bool. The annual `True` must
        # broadcast to True for every month — must NOT be coerced to
        # `True / 12 == 0.0833`. The numeric guard catches `bool ⊂ int`.
        household = {
            "people": {"person_1": {"is_incarcerated": {"2026": True}}}
        }

        normalized = _normalize_period_keys(household, us_system)

        flag_map = normalized["people"]["person_1"]["is_incarcerated"]
        for month in range(1, 13):
            assert flag_map[f"2026-{month:02d}"] is True

    def test__boolean_year_key__broadcasts_false_unchanged(self, us_system):
        household = {
            "people": {"person_1": {"is_incarcerated": {"2026": False}}}
        }

        normalized = _normalize_period_keys(household, us_system)

        flag_map = normalized["people"]["person_1"]["is_incarcerated"]
        for month in range(1, 13):
            assert flag_map[f"2026-{month:02d}"] is False

    def test__enum_year_key__broadcasts_unchanged(self, us_system):
        # `snap_utility_allowance_type` is a MONTH-defined Enum.
        household = {
            "spm_units": {
                "spm_unit_1": {"snap_utility_allowance_type": {"2026": "SUA"}}
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        utility_map = normalized["spm_units"]["spm_unit_1"][
            "snap_utility_allowance_type"
        ]
        for month in range(1, 13):
            assert utility_map[f"2026-{month:02d}"] == "SUA"

    def test__enum_year_input_with_monthly_output_request__gets_filled(
        self, us_system
    ):
        # Year input + null output request on a specific month: the year
        # value must reach that month so the engine doesn't read None and
        # return the variable's default.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_utility_allowance_type": {
                        "2026": "SUA",
                        "2026-06": None,
                    }
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        utility_map = normalized["spm_units"]["spm_unit_1"][
            "snap_utility_allowance_type"
        ]
        for month in range(1, 13):
            assert utility_map[f"2026-{month:02d}"] == "SUA"

    def test__enum_year_input_with_explicit_month_override__month_wins(
        self, us_system
    ):
        # `{"2026": "SUA", "2026-06": "LUA"}` -> June is LUA; other months
        # inherit the year-input "SUA". This lets partners express "SUA all
        # year except June".
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_utility_allowance_type": {
                        "2026": "SUA",
                        "2026-06": "LUA",
                    }
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        utility_map = normalized["spm_units"]["spm_unit_1"][
            "snap_utility_allowance_type"
        ]
        assert utility_map["2026-06"] == "LUA"
        for month in [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]:
            assert utility_map[f"2026-{month:02d}"] == "SUA"


# ---------------------------------------------------------------------------
# _normalize_period_keys: edges
# ---------------------------------------------------------------------------


class TestNormalizerEdges:
    def test__year_defined_variable__left_alone(self, us_system):
        # `employment_income` is YEAR-defined — annual key is correct as-is.
        household = {
            "people": {"person_1": {"employment_income": {"2026": 31932}}}
        }

        normalized = _normalize_period_keys(household, us_system)

        assert normalized["people"]["person_1"]["employment_income"] == {
            "2026": 31932
        }

    def test__year_defined_enum__left_alone(self, us_system):
        # `state_name` is YEAR-defined Enum — annual key is correct as-is.
        household = {
            "households": {"household_1": {"state_name": {"2026": "WA"}}}
        }

        normalized = _normalize_period_keys(household, us_system)

        assert normalized["households"]["household_1"]["state_name"] == {
            "2026": "WA"
        }

    def test__unknown_variable__left_alone(self, us_system):
        # Unknown variable names must not blow up the normalizer.
        household = {
            "spm_units": {"spm_unit_1": {"not_a_real_variable": {"2026": 999}}}
        }

        normalized = _normalize_period_keys(household, us_system)

        assert normalized["spm_units"]["spm_unit_1"][
            "not_a_real_variable"
        ] == {"2026": 999}

    def test__axes_key__skipped(self, us_system):
        # `axes` is a list — the normalizer must not misread it as an
        # entity-plural map.
        household = {
            "axes": [{"name": "employment_income", "count": 5}],
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"2026": 1200}}
            },
        }

        normalized = _normalize_period_keys(household, us_system)

        # The list survives untouched.
        assert normalized["axes"] == [
            {"name": "employment_income", "count": 5}
        ]
        # The MONTH var is still expanded.
        assert (
            normalized["spm_units"]["spm_unit_1"]["snap_earned_income"][
                "2026-06"
            ]
            == 100
        )

    def test__non_string_period_key__does_not_crash(self, us_system):
        # Pydantic schemas should keep non-string keys out, but defend in
        # depth: an unparseable key shouldn't blow up the normalizer.
        household = {
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"not-a-period": 100}}
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        assert normalized["spm_units"]["spm_unit_1"]["snap_earned_income"] == {
            "not-a-period": 100
        }

    def test__original_household_not_mutated(self, us_system):
        # The normalizer must return a fresh dict so the response can echo
        # the partner's keys verbatim.
        household = {
            "spm_units": {"spm_unit_1": {"snap_earned_income": {"2026": 1200}}}
        }

        normalized = _normalize_period_keys(household, us_system)

        assert household["spm_units"]["spm_unit_1"]["snap_earned_income"] == {
            "2026": 1200
        }
        # And the returned dict is a different object.
        assert normalized is not household


# ---------------------------------------------------------------------------
# validate_period_budgets: explicit months exceeding annual -> 400
# ---------------------------------------------------------------------------


class TestValidatePeriodBudgets:
    def test__explicit_months_below_annual__no_error(self, us_system):
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 1200, "2026-06": 600}
                }
            }
        }

        validate_period_budgets(household, us_system)  # must not raise

    def test__explicit_months_equal_annual__no_error(self, us_system):
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        "2026": 600,
                        "2026-01": 300,
                        "2026-02": 300,
                    }
                }
            }
        }

        validate_period_budgets(household, us_system)  # must not raise

    def test__explicit_months_exceed_annual__raises_value_error(
        self, us_system
    ):
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        "2026": 1200,
                        "2026-06": 999,
                        "2026-07": 999,
                    }
                }
            }
        }

        with pytest.raises(ValueError) as exc_info:
            validate_period_budgets(household, us_system)

        message = str(exc_info.value)
        assert "snap_earned_income" in message
        assert "spm_unit_1" in message
        assert "2026" in message
        assert "1998" in message
        assert "1200" in message

    def test__bool_var_does_not_trigger_budget_check(self, us_system):
        # Budget logic is numeric-only. Passing both year + month bools
        # must not raise even though the "sum" doesn't make sense.
        household = {
            "people": {
                "person_1": {
                    "is_incarcerated": {"2026": True, "2026-06": False}
                }
            }
        }

        validate_period_budgets(household, us_system)  # must not raise

    def test__year_defined_var_skipped(self, us_system):
        # YEAR-defined vars don't have the budget concept.
        household = {
            "people": {"person_1": {"employment_income": {"2026": 31932}}}
        }

        validate_period_budgets(household, us_system)  # must not raise

    def test__unknown_variable_skipped(self, us_system):
        household = {
            "spm_units": {
                "spm_unit_1": {"not_a_variable": {"2026": 100, "2026-01": 200}}
            }
        }

        validate_period_budgets(household, us_system)  # must not raise


# ---------------------------------------------------------------------------
# End-to-end SNAP matrix: post-fix household API matches v1 numerically
# ---------------------------------------------------------------------------


def _wa_household(income_map, output_key):
    """Build a single-person WA SNAP household with a configurable
    ``snap_gross_income`` input map + ``snap`` output request."""
    return {
        "people": {"person_1": {"age": {"2026": 34}, "rent": {"2026": 10800}}},
        "tax_units": {"tax_unit_1": {"members": ["person_1"]}},
        "spm_units": {
            "spm_unit_1": {
                "members": ["person_1"],
                "snap": {output_key: None},
                "snap_gross_income": dict(income_map),
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


# Each row pinned against parity with the hosted v1 API; the post-fix
# household API must return the same numbers.
_SNAP_MATRIX = [
    # (income_map, output_key, expected_snap)
    # Year-only inputs.
    ({"2026": 36000}, "2026", {"2026": 0.0}),
    ({"2026": 36000}, "2026-01", {"2026-01": 0.0}),
    ({"2026": 3600}, "2026", {"2026": 3596.0398}),
    ({"2026": 3600}, "2026-01", {"2026-01": 298.0}),
    # Single-month-only inputs (other 11 months default to 0).
    ({"2026-01": 36000}, "2026", {"2026": 3298.0398}),
    ({"2026-01": 36000}, "2026-01", {"2026-01": 0.0}),
    ({"2026-01": 3600}, "2026", {"2026": 3298.0398}),
    ({"2026-01": 3600}, "2026-01", {"2026-01": 0.0}),
    # Year + same-year month coherent (sum < annual): June pinned to $1800,
    # remainder ($1800/11 ≈ $163.64) distributes to the other 11 months.
    # Pinned against the v1 number — the case Anthony flagged in review.
    ({"2026": 3600, "2026-06": 1800}, "2026", {"2026": 3321.8796}),
]
_SNAP_MATRIX_IDS = [
    "A-O1",
    "A-O2",
    "B-O1",
    "B-O2",
    "C-O1",
    "C-O2",
    "D-O1",
    "D-O2",
    "Mixed-coherent",
]


@pytest.fixture(scope="module")
def us_country():
    return PolicyEngineCountry(country_package_name_us, country_id_us)


class TestSnapInputOutputMatrix:
    """End-to-end: the post-fix household API matches the hosted v1 API.

    Documents the input/output contract partners can rely on:

    - YEAR-keyed numeric input on a MONTH-defined variable distributes
      across the year (V/12 by default; explicit monthly values consume
      part of the budget and the remainder splits across the unset months).
    - MONTH-keyed input applies to that one month only; other months
      read the engine default.
    - YEAR-keyed output is the engine's sum across the 12 months.
    - MONTH-keyed output is the value for that single month.
    """

    @pytest.mark.parametrize(
        "income_map,output_key,expected_snap",
        _SNAP_MATRIX,
        ids=_SNAP_MATRIX_IDS,
    )
    def test__matches_v1_api_behavior(
        self,
        us_country,
        income_map,
        output_key,
        expected_snap,
    ):
        household = _wa_household(income_map, output_key)

        result, _ = us_country.calculate(
            household=household,
            reform=None,
            enable_ai_explainer=False,
        )

        snap = result["spm_units"]["spm_unit_1"]["snap"]
        assert snap.keys() == expected_snap.keys()
        # ±$0.05 absorbs cross-version float drift from numpy/pandas; the
        # expected values are pinned against hosted v1 API parity.
        for k in snap:
            assert snap[k] == pytest.approx(expected_snap[k], abs=0.05)

    def test__user_input_keys_are_echoed_unchanged(self, us_country):
        # Partners send `{"2026": V}` and must get `{"2026": V}` back even
        # though the engine internally sees the 12-month split.
        household = _wa_household({"2026": 31932}, "2026")

        result, _ = us_country.calculate(
            household=household,
            reform=None,
            enable_ai_explainer=False,
        )

        echoed = result["spm_units"]["spm_unit_1"]["snap_gross_income"]
        assert echoed == {"2026": 31932}

    def test__monthly_input_keys_are_also_echoed_unchanged(self, us_country):
        household = _wa_household({"2026-01": 3000}, "2026-01")

        result, _ = us_country.calculate(
            household=household,
            reform=None,
            enable_ai_explainer=False,
        )

        echoed = result["spm_units"]["spm_unit_1"]["snap_gross_income"]
        assert echoed == {"2026-01": 3000}
