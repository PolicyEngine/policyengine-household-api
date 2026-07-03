from dataclasses import dataclass
from unittest.mock import patch

import pytest

from policyengine_household_api.analytics.events import CalculateAnalyticsEvent
from policyengine_household_common.models.analytics import (
    AnalyticsContext,
    AvailabilityStatus,
    VariableUsageSummary,
)


@dataclass
class CalculateAnalyticsCapture:
    events: list[CalculateAnalyticsEvent]

    @property
    def event(self) -> CalculateAnalyticsEvent:
        return self.events[-1]

    @property
    def context(self) -> AnalyticsContext:
        return self.event.context

    @property
    def variable_summaries(self) -> tuple[VariableUsageSummary, ...]:
        return self.context.variable_summaries

    @property
    def unsupported_variable_count(self) -> int:
        return len(
            {
                item.variable_name
                for item in self.variable_summaries
                if item.availability_status is AvailabilityStatus.UNSUPPORTED
            }
        )

    def variable_summary(self, variable_name: str) -> VariableUsageSummary:
        return next(
            item
            for item in self.variable_summaries
            if item.variable_name == variable_name
        )


@pytest.fixture
def calculate_analytics_capture():
    events: list[CalculateAnalyticsEvent] = []
    with (
        patch(
            "policyengine_household_api.decorators.analytics.is_analytics_enabled",
            return_value=True,
        ),
        patch(
            "policyengine_household_api.decorators.analytics."
            "_sub_claim_from_validated_token",
            return_value="test-client@clients",
        ),
        patch(
            "policyengine_household_api.decorators.analytics."
            "enqueue_calculate_analytics_event",
            side_effect=events.append,
        ),
    ):
        yield CalculateAnalyticsCapture(events)
