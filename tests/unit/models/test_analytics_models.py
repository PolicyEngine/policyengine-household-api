from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from policyengine_household_analytics.orm import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)
from policyengine_household_analytics.legacy import (
    LEGACY_VISIT_REQUEST_NAMESPACE,
    legacy_visit_request_uuid,
)
from policyengine_household_common.models.analytics import (
    AnalyticsContext,
    AnalyticsHttpMethod,
    AnalyticsRecordSource,
    AvailabilityStatus,
    ModalResolvedChannel,
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
        requested_version="frontier",
        resolved_channel="frontier",
    )

    assert context.method is AnalyticsHttpMethod.POST
    assert context.resolved_channel is ModalResolvedChannel.FRONTIER
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
    assert CalculateRequest.__table__.c.record_source.info["options"] == tuple(
        source.value for source in AnalyticsRecordSource
    )
    assert CalculateRequest.__table__.c.resolved_channel.info[
        "options"
    ] == tuple(channel.value for channel in ModalResolvedChannel)
    assert CalculateRequestVariable.__table__.c.resolved_channel.info[
        "options"
    ] == tuple(channel.value for channel in ModalResolvedChannel)
    assert CalculateRequestVariable.__table__.c.source.info[
        "options"
    ] == tuple(source.value for source in VariableSource)
    assert CalculateRequestVariable.__table__.c.period_granularity.info[
        "options"
    ] == tuple(granularity.value for granularity in PeriodGranularity)
    assert CalculateRequestVariable.__table__.c.availability_status.info[
        "options"
    ] == tuple(status.value for status in AvailabilityStatus)


def test__calculate_request__supports_legacy_metadata_provenance():
    columns = CalculateRequest.__table__.c

    assert columns.country_id.nullable is True
    assert columns.record_source.nullable is False
    assert columns.record_source.default.arg == "live"
    assert columns.record_source.server_default.arg == "live"
    assert columns.variable_metadata_collected.nullable is False
    assert columns.variable_metadata_collected.default.arg is True

    existing_visit_id_index = next(
        index
        for index in CalculateRequest.__table__.indexes
        if index.name == "ix_calculate_requests_visit_id"
    )
    assert existing_visit_id_index.unique is False


def test__legacy_visit_request_uuid__is_stable_and_visit_specific():
    assert str(LEGACY_VISIT_REQUEST_NAMESPACE) == (
        "5b06406a-e2e2-5e53-a25f-9082a2aa7849"
    )
    assert legacy_visit_request_uuid(1) == (
        "1f69e5d0-eae2-59cb-9d59-bd8de1ee8b78"
    )
    assert legacy_visit_request_uuid(139) == (
        "6e9bb15c-f9c4-5255-a2c4-fa2510af8832"
    )
    assert legacy_visit_request_uuid(1) == legacy_visit_request_uuid(1)


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
