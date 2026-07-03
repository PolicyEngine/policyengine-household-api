from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError

from policyengine_household_api.analytics.events import CalculateAnalyticsEvent
from policyengine_household_api.data.analytics_setup import db
from policyengine_household_api.data.models import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)
from policyengine_household_common.models.analytics import (
    AnalyticsContext,
    VariableUsageSummary,
)
from policyengine_household_common.variable_usage_analytics import (
    stored_variable_name,
)

logger = logging.getLogger(__name__)


def record_calculate_analytics_event(
    event: CalculateAnalyticsEvent,
) -> None:
    record_analytics(event.context, event.response_status_code)


def record_analytics(
    context: AnalyticsContext | None,
    response_status_code: int | None,
) -> None:
    if context is None:
        return

    if _calculate_request_exists(context):
        return

    try:
        visit = _build_visit(context)
        db.session.add(visit)
        db.session.flush()
        visit_id = getattr(visit, "id", None)

        variable_summaries = context.variable_summaries
        calculate_request = _build_calculate_request(
            context,
            response_status_code,
            variable_summaries,
            visit_id,
        )

        if calculate_request is not None:
            db.session.add(calculate_request)
            db.session.flush()
            for summary in variable_summaries:
                db.session.add(
                    _build_calculate_request_variable(
                        calculate_request,
                        summary,
                    )
                )

        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if _calculate_request_exists(context):
            return
        logger.exception("Failed to log analytics due to integrity error")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to log analytics: {e}")
        raise


def _calculate_request_exists(context: AnalyticsContext) -> bool:
    if not context.record_calculate_request:
        return False
    return (
        db.session.query(CalculateRequest)
        .filter_by(request_uuid=context.request_uuid)
        .first()
        is not None
    )


def _build_visit(context: AnalyticsContext) -> Visit:
    visit = Visit()
    visit.client_id = context.client_id
    visit.api_version = context.api_version
    visit.endpoint = context.endpoint
    visit.method = context.method.value
    visit.content_length_bytes = context.content_length_bytes
    visit.datetime = context.created_at
    return visit


def _build_calculate_request(
    context: AnalyticsContext,
    response_status_code: int | None,
    variable_summaries: tuple[VariableUsageSummary, ...],
    visit_id: int | None,
) -> CalculateRequest | None:
    if not context.record_calculate_request:
        return None
    if visit_id is None:
        raise ValueError("Visit ID is required for calculate analytics")

    distinct_variable_names = {
        summary.variable_name for summary in variable_summaries
    }
    unsupported_variable_names = {
        summary.variable_name
        for summary in variable_summaries
        if summary.availability_status == "unsupported"
    }
    deprecated_allowlisted_variable_names = {
        summary.variable_name
        for summary in variable_summaries
        if summary.availability_status == "deprecated_allowlisted"
    }

    calculate_request = CalculateRequest()
    calculate_request.visit_id = visit_id
    calculate_request.request_uuid = context.request_uuid
    calculate_request.client_id = context.client_id
    calculate_request.api_version = context.api_version
    calculate_request.country_id = context.country_id
    calculate_request.model_version = context.model_version
    calculate_request.requested_version = context.requested_version
    calculate_request.resolved_channel = (
        context.resolved_channel.value if context.resolved_channel else None
    )
    calculate_request.endpoint = context.endpoint
    calculate_request.method = context.method.value
    calculate_request.content_length_bytes = context.content_length_bytes
    calculate_request.response_status_code = response_status_code
    calculate_request.distinct_variable_count = len(distinct_variable_names)
    calculate_request.unsupported_variable_count = len(
        unsupported_variable_names
    )
    calculate_request.deprecated_allowlisted_variable_count = len(
        deprecated_allowlisted_variable_names
    )
    calculate_request.created_at = context.created_at
    return calculate_request


def _build_calculate_request_variable(
    calculate_request: CalculateRequest,
    summary: VariableUsageSummary,
) -> CalculateRequestVariable:
    variable = CalculateRequestVariable()
    variable.request_id = calculate_request.id
    variable.client_id = calculate_request.client_id
    variable.created_at = calculate_request.created_at
    variable.country_id = calculate_request.country_id
    variable.api_version = calculate_request.api_version
    variable.model_version = calculate_request.model_version
    variable.requested_version = calculate_request.requested_version
    variable.resolved_channel = calculate_request.resolved_channel
    variable.response_status_code = calculate_request.response_status_code
    (
        variable.variable_name,
        variable.variable_name_truncated,
    ) = stored_variable_name(summary.variable_name)
    variable.entity_type = summary.entity_type
    variable.source = summary.source.value
    variable.period_granularity = summary.period_granularity.value
    variable.entity_count = summary.entity_count
    variable.period_count = summary.period_count
    variable.occurrence_count = summary.occurrence_count
    variable.availability_status = summary.availability_status.value
    return variable
