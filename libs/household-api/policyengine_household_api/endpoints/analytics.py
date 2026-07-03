from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any

from flask import Response, current_app, request
from sqlalchemy import func

from policyengine_household_analytics.analytics_setup import (
    initialize_analytics_db_if_enabled,
    is_analytics_enabled,
    is_analytics_schema_ready,
)
from policyengine_household_analytics.orm import (
    CalculateRequest,
    CalculateRequestVariable,
)
from policyengine_household_common.models.analytics import ModalResolvedChannel


DEFAULT_REQUEST_LIMIT = 1_000
MAX_REQUEST_LIMIT = 10_000
TRUE_VALUES = {"1", "true", "yes"}
FALSE_VALUES = {"0", "false", "no"}
ANALYTICS_STORAGE_INITIALIZED_CONFIG_KEY = (
    "POLICYENGINE_ANALYTICS_STORAGE_INITIALIZED"
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalculateAnalyticsQuery:
    start_time: datetime | None
    end_time: datetime | None
    requested_version: str | None
    resolved_channel: str | None
    unique: bool
    limit: int


def get_calculate_analytics_requests() -> Response:
    try:
        query = _parse_query_args()
    except ValueError as e:
        return _json_response(
            {"status": "error", "message": str(e)},
            status=400,
        )

    analytics_storage_error = _analytics_storage_error_response()
    if analytics_storage_error is not None:
        return analytics_storage_error

    response_body: dict[str, Any] = {
        "status": "ok",
        "message": None,
        "start_time": _datetime_to_json(query.start_time),
        "end_time": _datetime_to_json(query.end_time),
        "requested_version": query.requested_version,
        "resolved_channel": query.resolved_channel,
        "unique": query.unique,
    }
    if query.unique:
        response_body["unique_keys"] = _unique_variable_keys(query)
    else:
        response_body["requests"] = _calculate_requests(query)

    return _json_response(response_body)


def _analytics_storage_error_response() -> Response | None:
    if not is_analytics_enabled():
        return _json_response(
            {
                "status": "error",
                "message": "Analytics is not enabled for this API instance.",
            },
            status=503,
        )

    try:
        _ensure_analytics_storage_initialized()
    except Exception:
        logger.warning(
            "Analytics storage is unavailable.",
            exc_info=True,
        )
        return _json_response(
            {
                "status": "error",
                "message": "Analytics storage is not ready.",
            },
            status=503,
        )

    if not is_analytics_schema_ready():
        return _json_response(
            {
                "status": "error",
                "message": "Analytics storage is not ready.",
            },
            status=503,
        )

    return None


def _ensure_analytics_storage_initialized() -> None:
    app = current_app._get_current_object()
    if app.config.get(ANALYTICS_STORAGE_INITIALIZED_CONFIG_KEY):
        return

    initialize_analytics_db_if_enabled(app)

    app.config[ANALYTICS_STORAGE_INITIALIZED_CONFIG_KEY] = True


def _parse_query_args() -> CalculateAnalyticsQuery:
    start_time = _parse_optional_datetime(
        _first_query_arg("start_time", "start"),
        "start_time",
    )
    end_time = _parse_optional_datetime(
        _first_query_arg("end_time", "end"),
        "end_time",
    )
    if start_time and end_time and start_time > end_time:
        raise ValueError("`start_time` must be before or equal to `end_time`")

    return CalculateAnalyticsQuery(
        start_time=start_time,
        end_time=end_time,
        requested_version=_parse_optional_string(
            request.args.get("requested_version")
        ),
        resolved_channel=_parse_resolved_channel(
            request.args.get("resolved_channel")
        ),
        unique=_parse_bool(request.args.get("unique"), default=False),
        limit=_parse_limit(request.args.get("limit")),
    )


def _first_query_arg(*names: str) -> str | None:
    for name in names:
        value = request.args.get(name)
        if value:
            return value
    return None


def _parse_optional_datetime(
    value: str | None,
    name: str,
) -> datetime | None:
    if value is None:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"`{name}` must be an ISO 8601 datetime") from e

    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError("`unique` must be true or false")


def _parse_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_resolved_channel(value: str | None) -> str | None:
    value = _parse_optional_string(value)
    if value is None:
        return None
    if value not in {channel.value for channel in ModalResolvedChannel}:
        allowed = ", ".join(channel.value for channel in ModalResolvedChannel)
        raise ValueError(f"`resolved_channel` must be one of: {allowed}")
    return value


def _parse_limit(value: str | None) -> int:
    if value is None:
        return DEFAULT_REQUEST_LIMIT

    try:
        limit = int(value)
    except ValueError as e:
        raise ValueError("`limit` must be an integer") from e

    if limit < 1 or limit > MAX_REQUEST_LIMIT:
        raise ValueError(f"`limit` must be between 1 and {MAX_REQUEST_LIMIT}")
    return limit


def _calculate_requests(
    query: CalculateAnalyticsQuery,
) -> list[dict[str, Any]]:
    request_query = _apply_filters(CalculateRequest.query, query)
    calculate_requests = (
        request_query.order_by(CalculateRequest.created_at.desc())
        .limit(query.limit)
        .all()
    )
    if not calculate_requests:
        return []

    variables_by_request_id = _variables_by_request_id(
        [calculate_request.id for calculate_request in calculate_requests]
    )
    return [
        _request_to_dict(
            calculate_request,
            variables_by_request_id.get(calculate_request.id, []),
        )
        for calculate_request in calculate_requests
    ]


def _variables_by_request_id(
    request_ids: list[int],
) -> dict[int, list[CalculateRequestVariable]]:
    variable_rows = (
        CalculateRequestVariable.query.filter(
            CalculateRequestVariable.request_id.in_(request_ids)
        )
        .order_by(
            CalculateRequestVariable.request_id,
            CalculateRequestVariable.variable_name,
            CalculateRequestVariable.entity_type,
            CalculateRequestVariable.source,
        )
        .all()
    )
    variables_by_request_id: dict[int, list[CalculateRequestVariable]] = {}
    for variable_row in variable_rows:
        variables_by_request_id.setdefault(
            variable_row.request_id,
            [],
        ).append(variable_row)
    return variables_by_request_id


def _unique_variable_keys(
    query: CalculateAnalyticsQuery,
) -> list[dict[str, Any]]:
    variable_query = _apply_filters(CalculateRequestVariable.query, query)
    rows = (
        variable_query.with_entities(
            CalculateRequestVariable.variable_name,
            CalculateRequestVariable.entity_type,
            CalculateRequestVariable.source,
            CalculateRequestVariable.period_granularity,
            CalculateRequestVariable.availability_status,
            CalculateRequestVariable.variable_name_truncated,
            func.count(func.distinct(CalculateRequestVariable.request_id)),
            func.sum(CalculateRequestVariable.occurrence_count),
            func.min(CalculateRequestVariable.created_at),
            func.max(CalculateRequestVariable.created_at),
        )
        .group_by(
            CalculateRequestVariable.variable_name,
            CalculateRequestVariable.entity_type,
            CalculateRequestVariable.source,
            CalculateRequestVariable.period_granularity,
            CalculateRequestVariable.availability_status,
            CalculateRequestVariable.variable_name_truncated,
        )
        .order_by(
            CalculateRequestVariable.variable_name,
            CalculateRequestVariable.entity_type,
            CalculateRequestVariable.source,
        )
        .all()
    )

    return [
        {
            "variable_name": row[0],
            "entity_type": row[1],
            "source": row[2],
            "period_granularity": row[3],
            "availability_status": row[4],
            "variable_name_truncated": bool(row[5]),
            "request_count": int(row[6] or 0),
            "occurrence_count": int(row[7] or 0),
            "first_seen": _datetime_to_json(row[8]),
            "last_seen": _datetime_to_json(row[9]),
        }
        for row in rows
    ]


def _apply_filters(query, filters: CalculateAnalyticsQuery):
    model = query.column_descriptions[0]["entity"]
    created_at = model.created_at
    if filters.start_time:
        query = query.filter(created_at >= filters.start_time)
    if filters.end_time:
        query = query.filter(created_at <= filters.end_time)
    if filters.requested_version:
        query = query.filter(
            model.requested_version == filters.requested_version
        )
    if filters.resolved_channel:
        query = query.filter(
            model.resolved_channel == filters.resolved_channel
        )
    return query


def _request_to_dict(
    calculate_request: CalculateRequest,
    variable_rows: list[CalculateRequestVariable],
) -> dict[str, Any]:
    return {
        "request_uuid": calculate_request.request_uuid,
        "created_at": _datetime_to_json(calculate_request.created_at),
        "api_version": calculate_request.api_version,
        "country_id": calculate_request.country_id,
        "model_version": calculate_request.model_version,
        "requested_version": calculate_request.requested_version,
        "resolved_channel": calculate_request.resolved_channel,
        "endpoint": calculate_request.endpoint,
        "method": calculate_request.method,
        "response_status_code": calculate_request.response_status_code,
        "distinct_variable_count": calculate_request.distinct_variable_count,
        "unsupported_variable_count": (
            calculate_request.unsupported_variable_count
        ),
        "deprecated_allowlisted_variable_count": (
            calculate_request.deprecated_allowlisted_variable_count
        ),
        "variables": [
            _variable_to_dict(variable_row) for variable_row in variable_rows
        ],
    }


def _variable_to_dict(
    variable_row: CalculateRequestVariable,
) -> dict[str, Any]:
    return {
        "variable_name": variable_row.variable_name,
        "entity_type": variable_row.entity_type,
        "source": variable_row.source,
        "period_granularity": variable_row.period_granularity,
        "entity_count": variable_row.entity_count,
        "period_count": variable_row.period_count,
        "occurrence_count": variable_row.occurrence_count,
        "availability_status": variable_row.availability_status,
        "variable_name_truncated": bool(variable_row.variable_name_truncated),
    }


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat() + "Z"


def _json_response(payload: dict[str, Any], *, status: int = 200) -> Response:
    return Response(
        json.dumps(payload),
        status=status,
        mimetype="application/json",
    )
