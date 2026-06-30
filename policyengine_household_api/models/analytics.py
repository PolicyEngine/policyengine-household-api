"""Typed analytics models used before persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsHttpMethod(StrEnum):
    DELETE = "DELETE"
    GET = "GET"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    PATCH = "PATCH"
    POST = "POST"
    PUT = "PUT"


class VariableSource(StrEnum):
    HOUSEHOLD_INPUT = "household_input"
    REQUESTED_OUTPUT = "requested_output"
    MIXED = "mixed"
    AXIS = "axis"


class AvailabilityStatus(StrEnum):
    SUPPORTED = "supported"
    DEPRECATED_ALLOWLISTED = "deprecated_allowlisted"
    UNSUPPORTED = "unsupported"


class PeriodGranularity(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    MIXED = "mixed"
    NONE = "none"
    UNKNOWN = "unknown"


class ModalResolvedChannel(StrEnum):
    CURRENT = "current"
    FRONTIER = "frontier"


class VariableUsageSummary(BaseModel):
    """A grouped, value-free variable usage record for one request."""

    model_config = ConfigDict(frozen=True)

    variable_name: str
    entity_type: str
    source: VariableSource
    period_granularity: PeriodGranularity
    entity_count: int
    period_count: int
    occurrence_count: int
    availability_status: AvailabilityStatus


class AnalyticsContext(BaseModel):
    """Request-scoped analytics metadata collected before endpoint execution."""

    model_config = ConfigDict(frozen=True)

    client_id: str | None
    request_uuid: str = Field(default_factory=lambda: str(uuid4()))
    api_version: str
    endpoint: str | None
    method: AnalyticsHttpMethod
    content_length_bytes: int | None
    created_at: datetime
    country_id: str | None
    model_version: str | None = None
    requested_version: str | None = None
    resolved_channel: ModalResolvedChannel | None = None
    variable_summaries: tuple[VariableUsageSummary, ...] = ()
    record_calculate_request: bool = False
