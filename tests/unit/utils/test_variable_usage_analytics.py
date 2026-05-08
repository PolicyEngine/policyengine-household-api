from types import SimpleNamespace

from policyengine_household_api.utils.variable_usage_analytics import (
    extract_variable_usage,
)


def fake_system():
    return SimpleNamespace(
        variables={
            "age": SimpleNamespace(
                entity=SimpleNamespace(key="person", plural="people")
            ),
            "employment_income": SimpleNamespace(
                entity=SimpleNamespace(key="person", plural="people")
            ),
            "ctc": SimpleNamespace(
                entity=SimpleNamespace(key="tax_unit", plural="tax_units")
            ),
            "state_code_str": SimpleNamespace(
                entity=SimpleNamespace(key="household", plural="households")
            ),
        },
        entities=[
            SimpleNamespace(key="person", plural="people"),
            SimpleNamespace(key="tax_unit", plural="tax_units"),
            SimpleNamespace(key="household", plural="households"),
        ],
    )


def summaries_by_key(household):
    summaries = extract_variable_usage(household, fake_system())
    return {
        (
            summary.variable_name,
            summary.entity_type,
            summary.source,
        ): summary
        for summary in summaries
    }


class TestExtractVariableUsage:
    def test__household_inputs__are_grouped_without_values_or_entity_ids(self):
        household = {
            "people": {
                "person_named_alice": {
                    "employment_income": {"2026": 50_000},
                },
                "person_named_bob": {
                    "employment_income": {"2026": 25_000},
                },
            }
        }

        summary = summaries_by_key(household)[
            ("employment_income", "person", "household_input")
        ]

        assert summary.entity_count == 2
        assert summary.period_count == 1
        assert summary.occurrence_count == 2
        assert summary.period_granularity == "year"
        assert summary.availability_status == "supported"
        assert summary.entity_type == "person"
        assert "alice" not in repr(summary)
        assert "bob" not in repr(summary)
        assert "50000" not in repr(summary)
        assert "25000" not in repr(summary)

    def test__requested_output__is_classified_from_null_values(self):
        household = {
            "tax_units": {
                "tax_unit": {
                    "ctc": {"2026": None},
                }
            }
        }

        summary = summaries_by_key(household)[
            ("ctc", "tax_unit", "requested_output")
        ]

        assert summary.entity_count == 1
        assert summary.period_count == 1
        assert summary.occurrence_count == 1
        assert summary.entity_type == "tax_unit"

    def test__axis_variables__exclude_axis_bounds(self):
        household = {
            "people": {"you": {"age": {"2026": 40}}},
            "axes": [
                {
                    "name": "employment_income",
                    "period": "2026",
                    "min": 0,
                    "max": 100_000,
                    "count": 5,
                }
            ],
        }

        summary = summaries_by_key(household)[
            ("employment_income", "person", "axis")
        ]

        assert summary.entity_count == 0
        assert summary.period_count == 1
        assert summary.occurrence_count == 1
        assert summary.period_granularity == "year"
        assert "100000" not in repr(summary)

    def test__deprecated_and_unsupported_variables__are_captured(self):
        household = {
            "people": {
                "you": {
                    "medical_out_of_pocket_expenses": {"2026": 100},
                    "definitely_not_a_variable": {"2026": 1},
                }
            }
        }

        summaries = summaries_by_key(household)

        assert (
            summaries[
                (
                    "medical_out_of_pocket_expenses",
                    "person",
                    "household_input",
                )
            ].availability_status
            == "deprecated_allowlisted"
        )
        assert (
            summaries[
                ("definitely_not_a_variable", "person", "household_input")
            ].availability_status
            == "unsupported"
        )

    def test__members__are_skipped(self):
        household = {
            "spm_units": {
                "spm_unit": {
                    "members": ["you"],
                }
            }
        }

        assert extract_variable_usage(household, fake_system()) == []

    def test__mixed_period_granularity__stores_granularity_not_period_keys(
        self,
    ):
        household = {
            "people": {
                "you": {
                    "employment_income": {
                        "2026": 50_000,
                        "2026-01": 4_000,
                    }
                }
            }
        }

        summary = summaries_by_key(household)[
            ("employment_income", "person", "household_input")
        ]

        assert summary.period_granularity == "mixed"
        assert summary.period_count == 2
        assert "2026-01" not in repr(summary)

    def test__unknown_entity_groups__store_unknown_entity_type(self):
        household = {
            "caller_supplied_group_name": {
                "caller_supplied_entity_name": {
                    "definitely_not_a_variable": {"2026": 1},
                }
            }
        }

        summary = summaries_by_key(household)[
            ("definitely_not_a_variable", "unknown", "household_input")
        ]

        assert summary.entity_type == "unknown"
        assert summary.availability_status == "unsupported"
        assert "caller_supplied_group_name" not in repr(summary)
        assert "caller_supplied_entity_name" not in repr(summary)
