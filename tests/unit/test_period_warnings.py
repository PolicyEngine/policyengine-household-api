"""Unit tests for the period-shape warning detector.

`detect_period_warnings` surfaces two kinds of structured warnings:

- ``OverlappingPeriodWarning`` — both annual and monthly inputs were
  given for the same year on the same variable; the household API keeps
  the later one (last write wins) and drops the other.
- ``PartialMonthlyInputWarning`` — partial monthly input paired with an
  annual output for the same year; the unset months read the engine's
  fallback and silently inflate the annual sum.

The endpoint serializes the dataclasses to strings on the wire.
"""

import json

import pytest
from policyengine_us import CountryTaxBenefitSystem

from policyengine_household_api.country import (
    OverlappingPeriodWarning,
    PartialMonthlyInputWarning,
    detect_period_warnings,
)


@pytest.fixture(scope="module")
def us_system():
    return CountryTaxBenefitSystem()


class TestDetectPeriodWarnings:
    def test__monthly_input_with_annual_output__warns(self, us_system):
        # The classic pitfall: only Jan keyed, but annual output requested.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                    "snap": {"2026": None},
                }
            },
        }

        warnings = detect_period_warnings(household, us_system)

        assert len(warnings) == 1
        warning = warnings[0]
        assert isinstance(warning, PartialMonthlyInputWarning)
        assert warning.variable == "snap_earned_income"
        assert warning.entity_plural == "spm_units"
        assert warning.entity_id == "spm_unit_1"
        assert warning.year == "2026"
        assert warning.months_set == (1,)

    def test__all_twelve_monthly_inputs_with_annual_output__no_warning(
        self, us_system
    ):
        # If the partner keys all 12 months, the annual sum is accurate.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        f"2026-{m:02d}": 2661 for m in range(1, 13)
                    },
                    "snap": {"2026": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__monthly_input_with_monthly_output__no_warning(self, us_system):
        # Per-month input + per-month output is a coherent request.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                    "snap": {"2026-01": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__annual_input_with_annual_output__no_warning(self, us_system):
        # Year-keyed input + year-keyed output is the recommended pattern.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 36000},
                    "snap": {"2026": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__annual_input_with_monthly_output__no_warning(self, us_system):
        # Annual input on a MONTH var still means every month is set after
        # normalization; a monthly output request reads one of those months.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 36000},
                    "snap": {"2026-01": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__year_defined_variable__never_warns(self, us_system):
        # YEAR-defined variables don't have the missing-month hazard.
        household = {
            "people": {
                "person_1": {
                    "employment_income": {"2026": 31932},
                    "ctc": {"2026": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__partial_months_three_set__warning_lists_them_in_order(
        self, us_system
    ):
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        "2026-06": 3000,
                        "2026-01": 3000,
                        "2026-03": 3000,
                    },
                    "snap": {"2026": None},
                }
            },
        }

        warnings = detect_period_warnings(household, us_system)

        assert len(warnings) == 1
        warning = warnings[0]
        # months_set is sorted regardless of input order.
        assert warning.months_set == (1, 3, 6)
        # And the rendered message lists them in that same chronological order.
        assert "(2026-01, 2026-03, 2026-06)" in warning.message
        assert "3 of 12" in warning.message

    def test__many_months_set__sample_truncates_to_three_with_ellipsis(
        self, us_system
    ):
        # When more than 3 months are set, the warning truncates with "..."
        # so the message stays readable. Exactly the first three (sorted)
        # are listed, followed by ", ...".
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {
                        f"2026-{m:02d}": 3000 for m in range(1, 8)
                    },
                    "snap": {"2026": None},
                }
            },
        }

        warnings = detect_period_warnings(household, us_system)

        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.months_set == (1, 2, 3, 4, 5, 6, 7)
        assert "(2026-01, 2026-02, 2026-03, ...)" in warning.message
        assert "7 of 12" in warning.message

    def test__multiple_offending_variables__each_gets_a_warning(
        self, us_system
    ):
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                    "snap_unearned_income": {"2026-01": 100},
                    "snap": {"2026": None},
                }
            },
        }

        warnings = detect_period_warnings(household, us_system)

        assert len(warnings) == 2
        names = {w.variable for w in warnings}
        assert names == {"snap_earned_income", "snap_unearned_income"}

    def test__no_annual_output_request__no_warning_even_for_partial_input(
        self, us_system
    ):
        # The hazard only materializes when the partner asks for an annual
        # sum. A purely monthly conversation is fine.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                    "snap": {"2026-01": None, "2026-02": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__year_defined_output_does_not_trigger_warning(self, us_system):
        # YEAR-defined variables don't have the missing-month hazard, so
        # an annual null on a YEAR-defined variable must not arm the
        # warning trigger for unrelated MONTH inputs.
        household = {
            "people": {
                "person_1": {
                    # `state_name` is YEAR-defined.
                    "state_name": {"2026": None},
                }
            },
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__different_year_input_and_output__no_warning(self, us_system):
        # If Jan-2026 input doesn't overlap with the 2027 annual output,
        # there's no hazard for that year.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                    "snap": {"2027": None},
                }
            },
        }

        assert detect_period_warnings(household, us_system) == []

    def test__axes_key_does_not_break_detection(self, us_system):
        # `axes` is a list — the detector must skip it without erroring.
        household = {
            "axes": [{"name": "employment_income", "count": 5}],
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000},
                    "snap": {"2026": None},
                }
            },
        }

        warnings = detect_period_warnings(household, us_system)

        assert len(warnings) == 1


class TestOverlappingPeriodWarning:
    def test__year_first_then_month__warns_with_dropped_year(self, us_system):
        # `{"2026": 1200, "2026-06": 600}` — last is the month → year drops.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 1200, "2026-06": 600},
                }
            }
        }

        warnings = detect_period_warnings(household, us_system)

        overlaps = [
            w for w in warnings if isinstance(w, OverlappingPeriodWarning)
        ]
        assert len(overlaps) == 1
        w = overlaps[0]
        assert w.variable == "snap_earned_income"
        assert w.entity_plural == "spm_units"
        assert w.entity_id == "spm_unit_1"
        assert w.year == "2026"
        assert w.kept_keys == ("2026-06",)
        assert w.dropped_keys == ("2026",)
        # The message phrases the rule in JSON-object terms (not chronology).
        assert "appears last in the JSON object" in w.message
        # And it documents the null-output exemption so partners aren't
        # confused by `{"2026": V, "2026-MM": null}` shapes.
        assert "Output-request slots (`null`) don't trigger this" in w.message

    def test__month_first_then_year__warns_with_dropped_month(self, us_system):
        # `{"2026-01": 100, "2026": 1200}` — last is the year → months drop.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 100, "2026": 1200},
                }
            }
        }

        warnings = detect_period_warnings(household, us_system)

        overlaps = [
            w for w in warnings if isinstance(w, OverlappingPeriodWarning)
        ]
        assert len(overlaps) == 1
        assert overlaps[0].kept_keys == ("2026",)
        assert overlaps[0].dropped_keys == ("2026-01",)

    def test__year_only_input__no_overlap_warning(self, us_system):
        # Baseline: a single annual entry is the recommended pattern,
        # not a conflict — must not produce an overlap warning.
        household = {
            "spm_units": {"spm_unit_1": {"snap_earned_income": {"2026": 1200}}}
        }

        warnings = detect_period_warnings(household, us_system)

        assert not any(
            isinstance(w, OverlappingPeriodWarning) for w in warnings
        )

    def test__monthly_only_input__no_overlap_warning(self, us_system):
        # Baseline: a single monthly entry is also a single-input shape
        # — no conflict, no overlap warning.
        household = {
            "spm_units": {
                "spm_unit_1": {"snap_earned_income": {"2026-01": 100}}
            }
        }

        warnings = detect_period_warnings(household, us_system)

        assert not any(
            isinstance(w, OverlappingPeriodWarning) for w in warnings
        )

    def test__year_input_with_monthly_null_output_is_not_an_overlap(
        self, us_system
    ):
        # `{"2026": 1200, "2026-06": null}` — the month is an output request,
        # not an input, so it doesn't conflict with the year input.
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026": 1200, "2026-06": None}
                }
            }
        }

        warnings = detect_period_warnings(household, us_system)

        assert not any(
            isinstance(w, OverlappingPeriodWarning) for w in warnings
        )

    def test__overlap_resolution_suppresses_partial_monthly_warning(
        self, us_system
    ):
        # `{"2026-01": 3000, "2026": 36000}` paired with `snap: {"2026": null}`.
        # Last is the year → month drops. After resolution there's no partial
        # monthly input, so the partial-monthly warning must NOT fire.
        # (Only the OverlappingPeriodWarning surfaces.)
        household = {
            "spm_units": {
                "spm_unit_1": {
                    "snap_earned_income": {"2026-01": 3000, "2026": 36000},
                    "snap": {"2026": None},
                }
            }
        }

        warnings = detect_period_warnings(household, us_system)

        kinds = {type(w).__name__ for w in warnings}
        assert "OverlappingPeriodWarning" in kinds
        assert "PartialMonthlyInputWarning" not in kinds


class TestEndpointAttachesWarnings:
    """Round-trip: the warning is exposed in the API response body as strings."""

    def test__partial_monthly_input__response_includes_warnings(self, client):
        from tests.fixtures.country import (
            valid_household_requesting_ctc_calculation,
        )

        household = {
            **valid_household_requesting_ctc_calculation,
            "spm_units": {
                "spm_unit": {
                    "members": ["you"],
                    "snap_earned_income": {"2024-01": 3000},
                    "snap": {"2024": None},
                }
            },
        }

        response = client.post("/us/calculate", json={"household": household})

        assert response.status_code == 200
        body = json.loads(response.data)
        assert "warnings" in body
        # On the wire warnings are strings, not dataclasses.
        assert all(isinstance(w, str) for w in body["warnings"])
        assert any("snap_earned_income" in w for w in body["warnings"])

    def test__well_formed_request__no_warnings_field_in_response(self, client):
        from tests.fixtures.country import (
            valid_household_requesting_ctc_calculation,
        )

        response = client.post(
            "/us/calculate",
            json={"household": valid_household_requesting_ctc_calculation},
        )

        assert response.status_code == 200
        body = json.loads(response.data)
        assert "warnings" not in body

    def test__overlap_warning_round_trips_through_flask_client(self, client):
        # Last-wins resolution depends on JSON-object insertion order
        # surviving the wire. CPython's `json.loads` preserves order,
        # but pydantic / Flask reconstruction could in theory reshuffle.
        # This end-to-end test pins the contract: send a year+month
        # payload, confirm the resulting OverlappingPeriodWarning string
        # names the monthly key as the kept input.
        from tests.fixtures.country import (
            valid_household_requesting_ctc_calculation,
        )

        household = {
            **valid_household_requesting_ctc_calculation,
            "spm_units": {
                "spm_unit": {
                    "members": ["you"],
                    "snap_earned_income": {"2024": 1200, "2024-06": 600},
                }
            },
        }

        response = client.post("/us/calculate", json={"household": household})

        assert response.status_code == 200
        body = json.loads(response.data)
        assert "warnings" in body
        overlap_warnings = [
            w for w in body["warnings"] if "appears last in the JSON" in w
        ]
        assert len(overlap_warnings) == 1
        # The monthly key (last in insertion order) was kept.
        assert "`2024-06`" in overlap_warnings[0]
        # The annual key (earlier) was dropped.
        assert "`2024`" in overlap_warnings[0]
