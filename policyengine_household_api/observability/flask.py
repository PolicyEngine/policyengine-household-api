from __future__ import annotations

from flask import Flask
from policyengine_observability.adapters.flask import (
    init_flask_observability,
)

from .config import ObservabilityConfig
from .runtime import ObservabilityRuntime
from .segments import SegmentName


def init_observability(app: Flask, *, service_role: str = "api") -> None:
    if app.extensions.get("policyengine_observability"):
        return

    config = ObservabilityConfig.from_env(service_role=service_role)
    init_flask_observability(
        app,
        config=config,
        runtime=ObservabilityRuntime(config),
        service_name=config.service_name,
        service_role=service_role,
        span_prefix=config.span_prefix,
        segment_registry=SegmentName,
    )
