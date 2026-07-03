from datetime import datetime, timezone
from unittest.mock import MagicMock

from policyengine_household_analytics.persistence import record_analytics
from policyengine_household_analytics.orm import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)
from policyengine_household_common.models.analytics import (
    AvailabilityStatus,
    AnalyticsContext,
    AnalyticsHttpMethod,
    ModalResolvedChannel,
    PeriodGranularity,
    VariableSource,
    VariableUsageSummary,
)


def test_record_analytics_duplicate_request_uuid_is_success(monkeypatch):
    from policyengine_household_api.analytics import persistence

    mock_db = MagicMock()
    existing_request = object()
    mock_db.session.query.return_value.filter_by.return_value.first.return_value = existing_request
    monkeypatch.setattr(persistence, "db", mock_db)
    context = AnalyticsContext(
        client_id="client-1",
        request_uuid="duplicate-request",
        api_version="0.1.0",
        endpoint="calculate",
        method=AnalyticsHttpMethod.POST,
        content_length_bytes=100,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        country_id="us",
        record_calculate_request=True,
    )

    record_analytics(context, 200)

    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()


def test_record_analytics_copies_metadata_and_truncates_variable_names(
    monkeypatch,
):
    from policyengine_household_api.analytics import persistence

    mock_db = MagicMock()
    mock_db.session.query.return_value.filter_by.return_value.first.return_value = None

    def assign_ids_on_flush():
        for added_call in mock_db.session.add.call_args_list:
            added_item = added_call.args[0]
            if isinstance(added_item, Visit):
                added_item.id = 1
            if isinstance(added_item, CalculateRequest):
                added_item.id = 2

    mock_db.session.flush.side_effect = assign_ids_on_flush
    monkeypatch.setattr(persistence, "db", mock_db)

    shared_prefix = "x" * 250
    first_variable_name = shared_prefix + "a"
    second_variable_name = shared_prefix + "b"
    context = AnalyticsContext(
        client_id="client-1",
        request_uuid="request-with-variables",
        api_version="0.1.0",
        endpoint="calculate",
        method=AnalyticsHttpMethod.POST,
        content_length_bytes=100,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        country_id="us",
        model_version="1.0.0",
        requested_version="1.691.1",
        resolved_channel=ModalResolvedChannel.FRONTIER,
        record_calculate_request=True,
        variable_summaries=(
            VariableUsageSummary(
                variable_name=first_variable_name,
                entity_type="person",
                source=VariableSource.HOUSEHOLD_INPUT,
                period_granularity=PeriodGranularity.YEAR,
                entity_count=1,
                period_count=1,
                occurrence_count=1,
                availability_status=AvailabilityStatus.UNSUPPORTED,
            ),
            VariableUsageSummary(
                variable_name=second_variable_name,
                entity_type="person",
                source=VariableSource.HOUSEHOLD_INPUT,
                period_granularity=PeriodGranularity.YEAR,
                entity_count=1,
                period_count=1,
                occurrence_count=1,
                availability_status=AvailabilityStatus.UNSUPPORTED,
            ),
        ),
    )

    record_analytics(context, 400)

    added = [call.args[0] for call in mock_db.session.add.call_args_list]
    calculate_request = next(
        item for item in added if isinstance(item, CalculateRequest)
    )
    variable_rows = [
        item for item in added if isinstance(item, CalculateRequestVariable)
    ]

    assert calculate_request.requested_version == "1.691.1"
    assert calculate_request.resolved_channel == "frontier"
    assert calculate_request.unsupported_variable_count == 2
    assert len(variable_rows) == 2
    assert {row.variable_name for row in variable_rows} == {
        shared_prefix + "..."
    }
    assert all(row.variable_name_truncated for row in variable_rows)
    assert {row.requested_version for row in variable_rows} == {"1.691.1"}
    assert {row.resolved_channel for row in variable_rows} == {"frontier"}
