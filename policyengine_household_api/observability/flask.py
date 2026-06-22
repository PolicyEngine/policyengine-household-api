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
