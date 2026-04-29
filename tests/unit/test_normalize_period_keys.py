"""Tests for the YEAR-key -> 12-monthly-keys normalization.

The normalizer is what makes the household API behave like the hosted v1
API (api.policyengine.org) when partners send a YEAR-period key on a
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


class TestYearMonthOverlapResolution:
    """When both year and same-year monthly inputs collide for a variable,
    the API keeps the group whose latest insertion is later in the dict."""

    def test__year_first_then_month__month_wins(self, us_system):
        # `{"2026": 1200, "2026-06": 600}` — month inserted last → year drops.
        # Only June is set; other 11 months default to 0 in the engine.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 1200, "2026-06": 600}
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert snap_map == {"2026-06": 600}

    def test__month_first_then_year__year_wins(self, us_system):
        # `{"2026-01": 100, "2026": 1200}` — year inserted last → month drops.
        # Year then expands as V/12 across all 12 months.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 100, "2026": 1200}
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        for month in range(1, 13):
            assert snap_map[f"2026-{month:02d}"] == 100  # 1200/12
        assert "2026" not in snap_map

    def test__multiple_months_then_year__all_months_drop(self, us_system):
        # `{"2026-01": 100, "2026-03": 200, "2026": 1200}` — year is last
        # among year+monthlies for 2026, so all explicit monthlies drop.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        "2026-01": 100,
                        "2026-03": 200,
                        "2026": 1200,
                    }
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        for month in range(1, 13):
            assert snap_map[f"2026-{month:02d}"] == 100  # 1200/12
        assert "2026" not in snap_map

    def test__year_then_multiple_months__year_drops_months_kept(
        self, us_system
    ):
        # `{"2026": 1200, "2026-01": 100, "2026-03": 200}` — last is a
        # monthly, so year drops; both monthlies survive.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        "2026": 1200,
                        "2026-01": 100,
                        "2026-03": 200,
                    }
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert snap_map == {"2026-01": 100, "2026-03": 200}

    def test__overrun_no_longer_an_error__last_wins_quietly(self, us_system):
        # The shape that used to raise (sum of monthlies > annual) is now
        # resolved — last wins, the budget concept is gone.
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

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        # Last is 2026-07 (a month), so year drops; both monthlies survive.
        assert snap_map == {"2026-06": 999, "2026-07": 999}

    def test__null_output_request_does_not_count_as_overlap(self, us_system):
        # `{"2026-01": 100, "2026": null}` — the year-keyed null is an
        # output request, exempt from resolution. The monthly input survives.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 100, "2026": None}
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        assert snap_map == {"2026-01": 100, "2026": None}

    def test__different_years_do_not_collide(self, us_system):
        # `{"2026": 1200, "2027-06": 600}` — months and year are for
        # different years, so there's no overlap. Each survives.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 1200, "2027-06": 600}
                }
            }
        }

        normalized = _normalize_period_keys(household, us_system)

        snap_map = normalized["spm_units"]["spm_unit_1"]["snap_earned_income"]
        # 2026 was distributed (V/12 = 100); 2027-06 untouched.
        assert snap_map["2026-01"] == 100
        assert snap_map["2027-06"] == 600
        assert "2026" not in snap_map


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

    def test__enum_year_input_then_explicit_month__month_wins_year_drops(
        self, us_system
    ):
        # `{"2026": "SUA", "2026-06": "LUA"}` — last-wins: 2026-06 is later
        # in insertion order, so the year drops. Only June is set; other
        # 11 months read the engine default. The partner sees an
        # OverlappingPeriodWarning explaining the resolution.
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
        assert utility_map == {"2026-06": "LUA"}


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
# End-to-end SNAP matrix
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


# Year-only or month-only matrix rows are pinned against parity with the
# hosted v1 API — the post-fix household API must return the same numbers.
# (The mixed year+month case is covered separately because the household
# API's last-wins resolution diverges from v1's redistribute behavior.)
_SNAP_MATRIX = [
    # (income_map, output_key, expected_snap)
    # Year-only inputs (4 income/output combinations).
    ({"2026": 36000}, "2026", {"2026": 0.0}),
    ({"2026": 36000}, "2026-01", {"2026-01": 0.0}),
    ({"2026": 3600}, "2026", {"2026": 3596.0398}),
    ({"2026": 3600}, "2026-01", {"2026-01": 298.0}),
    # Single-month-only inputs (other 11 months default to 0).
    ({"2026-01": 36000}, "2026", {"2026": 3298.0398}),
    ({"2026-01": 36000}, "2026-01", {"2026-01": 0.0}),
    ({"2026-01": 3600}, "2026", {"2026": 3298.0398}),
    ({"2026-01": 3600}, "2026-01", {"2026-01": 0.0}),
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
]


@pytest.fixture(scope="module")
def us_country():
    return PolicyEngineCountry(country_package_name_us, country_id_us)


class TestSnapInputOutputMatrix:
    """End-to-end: post-fix household API matches the hosted v1 API.

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
