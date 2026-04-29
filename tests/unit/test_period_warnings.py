"""Unit tests for the period-shape warning detector.

These tests cover `detect_period_warnings`, which surfaces request shapes
that produce plausible-but-wrong numbers — most notably, single-month input
on a MONTH-defined variable paired with an annual output request.

The detector returns structured `PartialMonthlyInputWarning` dataclasses;
the endpoint serializes them to strings on the wire.
"""

import json

import pytest
from policyengine_us import CountryTaxBenefitSystem

from policyengine_household_api.country import (
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
