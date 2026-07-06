from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from policyengine_household_common.models.analytics import AnalyticsContext


class CalculateAnalyticsEvent(BaseModel):
    """Value-free analytics event persisted outside the request path."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    context: AnalyticsContext
    response_status_code: int | None = None
