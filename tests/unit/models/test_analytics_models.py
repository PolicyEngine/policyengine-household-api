from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from policyengine_household_api.data.models import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)
from policyengine_household_api.models.analytics import (
    AnalyticsContext,
    AnalyticsHttpMethod,
    AvailabilityStatus,
    PeriodGranularity,
    VariableSource,
    VariableUsageSummary,
)


def test__analytics_context__is_typed_model():
    context = AnalyticsContext(
        client_id="test-client",
        api_version="1.0.0",
        endpoint="calculate",
        method="POST",
        content_length_bytes=123,
        created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        country_id="us",
    )

    assert context.method is AnalyticsHttpMethod.POST
    assert context.record_calculate_request is False
    with pytest.raises(ValidationError):
        AnalyticsContext(
            client_id="test-client",
            api_version="1.0.0",
            endpoint="calculate",
            method="NOT_A_METHOD",
            content_length_bytes=123,
            created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
            country_id="us",
        )


def test__analytics_sqlalchemy_rows__define_fixed_options():
    assert Visit.__table__.c.method.info["options"] == tuple(
        method.value for method in AnalyticsHttpMethod
    )
    assert CalculateRequest.__table__.c.method.info["options"] == tuple(
        method.value for method in AnalyticsHttpMethod
    )
    assert CalculateRequestVariable.__table__.c.source.info["options"] == tuple(
        source.value for source in VariableSource
    )
    assert (
        CalculateRequestVariable.__table__.c.period_granularity.info[
            "options"
        ]
        == tuple(granularity.value for granularity in PeriodGranularity)
    )
    assert (
        CalculateRequestVariable.__table__.c.availability_status.info[
            "options"
        ]
        == tuple(status.value for status in AvailabilityStatus)
    )


def test__variable_usage_summary__defines_fixed_row_options():
    summary = VariableUsageSummary(
        variable_name="employment_income",
        entity_type="person",
        source="household_input",
        period_granularity="year",
        entity_count=1,
        period_count=1,
        occurrence_count=1,
        availability_status="supported",
    )

    assert summary.source is VariableSource.HOUSEHOLD_INPUT
    assert summary.period_granularity is PeriodGranularity.YEAR
    assert summary.availability_status is AvailabilityStatus.SUPPORTED

    with pytest.raises(ValidationError):
        VariableUsageSummary(
            variable_name="employment_income",
            entity_type="person",
            source="not_a_source",
            period_granularity="year",
            entity_count=1,
            period_count=1,
            occurrence_count=1,
            availability_status="supported",
        )
