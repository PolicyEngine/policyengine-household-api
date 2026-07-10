from __future__ import annotations

from dataclasses import replace
import os

from flask import Flask
from policyengine_observability import ObservabilityConfig
from policyengine_observability import ObservabilityRuntime
from policyengine_observability import set_attribute
from policyengine_observability.adapters.flask import (
    init_flask_observability,
)

from .segments import SegmentName


SERVICE_NAME = "policyengine-household-api"
SPAN_PREFIX = "household"
HOUSEHOLD_METRIC_ATTRIBUTE_KEYS = (
    "api_version",
    "cloud_run_configuration",
    "cloud_run_revision",
    "cloud_run_service",
    "deprecated_warning_count",
    "google_cloud_project",
    "modal_app_name",
    "modal_environment",
    "modal_function_name",
    "platform",
    "runtime_role",
    "model_version",
    "period_warning_count",
    "variable_error_count",
)


def _environment() -> str:
    return (
        os.getenv("OBSERVABILITY_ENVIRONMENT")
        or os.getenv("DEPLOYMENT_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("APP__ENVIRONMENT")
        or "local"
    )


def _service_role(default: str) -> str:
    return (
        os.getenv("OBSERVABILITY_SERVICE_ROLE")
        or os.getenv("OBSERVABILITY_RUNTIME_ROLE")
        or default
    )


def _platform() -> str:
    configured = os.getenv("OBSERVABILITY_PLATFORM")
    if configured:
        return configured
    if os.getenv("K_SERVICE") or os.getenv("K_REVISION"):
        return "google_cloud_run"
    if (
        os.getenv("MODAL_ENVIRONMENT")
        or os.getenv("MODAL_TASK_ID")
        or os.getenv("OBSERVABILITY_MODAL_APP_NAME")
    ):
        return "modal"
    return "local"


def _metadata(service_role: str, platform: str) -> dict[str, str]:
    values = {
        "platform": platform,
        "runtime_role": os.getenv("OBSERVABILITY_RUNTIME_ROLE")
        or service_role,
        "cloud_run_service": os.getenv("K_SERVICE"),
        "cloud_run_revision": os.getenv("K_REVISION"),
        "cloud_run_configuration": os.getenv("K_CONFIGURATION"),
        "google_cloud_project": os.getenv("OBSERVABILITY_GOOGLE_CLOUD_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
        or os.getenv("GCLOUD_PROJECT"),
        "modal_environment": os.getenv("MODAL_ENVIRONMENT"),
        "modal_app_name": os.getenv("OBSERVABILITY_MODAL_APP_NAME"),
        "modal_function_name": os.getenv("OBSERVABILITY_MODAL_FUNCTION_NAME"),
    }
    return {key: value for key, value in values.items() if value}


def configure_process_observability(
    *,
    platform: str,
    service_role: str,
    runtime_role: str | None = None,
    modal_app_name: str | None = None,
    modal_function_name: str | None = None,
) -> None:
    os.environ.setdefault("OBSERVABILITY_PLATFORM", platform)
    os.environ.setdefault("OBSERVABILITY_SERVICE_ROLE", service_role)
    os.environ.setdefault(
        "OBSERVABILITY_RUNTIME_ROLE",
        runtime_role or service_role,
    )
    if modal_app_name:
        os.environ.setdefault("OBSERVABILITY_MODAL_APP_NAME", modal_app_name)
    if modal_function_name:
        os.environ.setdefault(
            "OBSERVABILITY_MODAL_FUNCTION_NAME",
            modal_function_name,
        )


def init_observability(app: Flask, *, service_role: str = "api") -> None:
    if app.extensions.get("policyengine_observability"):
        return

    service_role = _service_role(service_role)
    platform = _platform()
    # Log routing is delegated to the package's log profiles: "auto"
    # resolves to gcp-agent on Cloud Run (google-formatted stdout,
    # agent-ingested) and gcp-direct on Modal (stdout plus queued Cloud
    # Logging writes). Anywhere without a platform marker keeps the
    # stdout default. Household platform detection is made authoritative
    # for that resolution — it accepts markers the package's own
    # auto-detection does not (K_REVISION, OBSERVABILITY_MODAL_APP_NAME),
    # and routing must never disagree with the platform we stamp on
    # request metadata. The variable is pinned only while the config is
    # built so no env state leaks into the process.
    pin_platform = "OBSERVABILITY_PLATFORM" not in os.environ
    if pin_platform:
        os.environ["OBSERVABILITY_PLATFORM"] = platform
    try:
        config = replace(
            ObservabilityConfig.from_env(
                service_name=SERVICE_NAME,
                service_role=service_role,
                span_prefix=SPAN_PREFIX,
                extra_metric_attribute_keys=HOUSEHOLD_METRIC_ATTRIBUTE_KEYS,
            ),
            environment=_environment(),
        )
    finally:
        if pin_platform:
            os.environ.pop("OBSERVABILITY_PLATFORM", None)
    init_flask_observability(
        app,
        config=config,
        runtime=ObservabilityRuntime(config, segment_registry=SegmentName),
        service_name=SERVICE_NAME,
        service_role=service_role,
        span_prefix=SPAN_PREFIX,
        segment_registry=SegmentName,
    )

    metadata = _metadata(service_role, platform)

    @app.before_request
    def _set_observability_metadata() -> None:
        for key, value in metadata.items():
            set_attribute(key, value)
