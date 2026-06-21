from __future__ import annotations

from flask import Flask

from .config import ObservabilityConfig
from .runtime import ObservabilityRuntime
from .runtime import set_observability_runtime


def init_observability(app: Flask, *, service_role: str = "api") -> None:
    if app.extensions.get("policyengine_observability"):
        return

    config = ObservabilityConfig.from_env(service_role=service_role)
    runtime = ObservabilityRuntime(config)
    runtime.configure()
    app.extensions["policyengine_observability"] = runtime
    set_observability_runtime(runtime)
    runtime.instrument_flask(app)
