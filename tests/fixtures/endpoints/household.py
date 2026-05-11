from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from policyengine_household_api.data.models import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)


@dataclass
class CalculateAnalyticsCapture:
    db: MagicMock

    @property
    def added(self):
        return [call.args[0] for call in self.db.session.add.call_args_list]

    @property
    def calculate_request(self) -> CalculateRequest:
        return next(
            item for item in self.added if isinstance(item, CalculateRequest)
        )

    @property
    def variable_rows(self) -> list[CalculateRequestVariable]:
        return [
            item
            for item in self.added
            if isinstance(item, CalculateRequestVariable)
        ]

    def variable_row(self, variable_name: str) -> CalculateRequestVariable:
        return next(
            item
            for item in self.variable_rows
            if item.variable_name == variable_name
        )


@pytest.fixture
def calculate_analytics_capture():
    with (
        patch(
            "policyengine_household_api.decorators.analytics.is_analytics_enabled",
            return_value=True,
        ),
        patch(
            "policyengine_household_api.decorators.analytics._verified_sub_claim",
            return_value="test-client@clients",
        ),
        patch("policyengine_household_api.decorators.analytics.db") as mock_db,
    ):

        def assign_ids_on_flush():
            for added_call in mock_db.session.add.call_args_list:
                added_item = added_call.args[0]
                if isinstance(added_item, Visit):
                    added_item.id = 1
                if isinstance(added_item, CalculateRequest):
                    added_item.id = 2

        mock_db.session.flush.side_effect = assign_ids_on_flush
        yield CalculateAnalyticsCapture(mock_db)


@pytest.fixture
def ai_explainer_tracer_failure():
    with patch(
        "policyengine_household_api.country.generate_computation_tree",
        side_effect=RuntimeError("tracer down"),
    ) as mock_tracer:
        yield mock_tracer
