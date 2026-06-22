from __future__ import annotations

from dataclasses import replace
import os

from flask import Flask
from policyengine_observability import ObservabilityConfig
from policyengine_observability import ObservabilityRuntime
from policyengine_observability.adapters.flask import (
    init_flask_observability,
)

from policyengine_household_api.utils.config_loader import get_config_value

from .segments import SegmentName


SERVICE_NAME = "policyengine-household-api"
SPAN_PREFIX = "household"
HOUSEHOLD_METRIC_ATTRIBUTE_KEYS = (
    "api_version",
    "deprecated_warning_count",
    "enable_ai_explainer",
    "modal_app_name",
    "model_version",
    "period_warning_count",
    "variable_error_count",
)


def _environment() -> str:
    return (
        os.getenv("OBSERVABILITY_ENVIRONMENT")
        or os.getenv("DEPLOYMENT_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or str(get_config_value("app.environment", "development"))
    )


def init_observability(app: Flask, *, service_role: str = "api") -> None:
    if app.extensions.get("policyengine_observability"):
        return

    config = replace(
        ObservabilityConfig.from_env(
            service_name=SERVICE_NAME,
            service_role=service_role,
            span_prefix=SPAN_PREFIX,
            extra_metric_attribute_keys=HOUSEHOLD_METRIC_ATTRIBUTE_KEYS,
        ),
        environment=_environment(),
    )
    init_flask_observability(
        app,
        config=config,
        runtime=ObservabilityRuntime(config, segment_registry=SegmentName),
        service_name=SERVICE_NAME,
        service_role=service_role,
        span_prefix=SPAN_PREFIX,
        segment_registry=SegmentName,
    )
