from __future__ import annotations

from dataclasses import dataclass
import logging
import os

from policyengine_household_api.utils.config_loader import get_config_value


def _bool_from_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _environment() -> str:
    return (
        os.getenv("OBSERVABILITY_ENVIRONMENT")
        or os.getenv("DEPLOYMENT_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or str(get_config_value("app.environment", "development"))
    )


@dataclass(frozen=True)
class ObservabilityConfig:
    service_name: str = "policyengine-household-api"
    service_role: str = "api"
    environment: str = "development"
    enabled: bool = True
    request_logs_enabled: bool = True
    log_raw_ip: bool = True
    log_level: int = logging.INFO
    otlp_endpoint: str | None = None

    @classmethod
    def from_env(cls, *, service_role: str) -> "ObservabilityConfig":
        level_name = os.getenv("OBSERVABILITY_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, level_name, logging.INFO)
        return cls(
            service_name=os.getenv(
                "OBSERVABILITY_SERVICE_NAME",
                os.getenv("OTEL_SERVICE_NAME", cls.service_name),
            ),
            service_role=service_role,
            environment=_environment(),
            enabled=_bool_from_env("OBSERVABILITY_ENABLED", True),
            request_logs_enabled=_bool_from_env(
                "OBSERVABILITY_REQUEST_LOGS_ENABLED",
                True,
            ),
            log_raw_ip=_bool_from_env("OBSERVABILITY_LOG_RAW_IP", True),
            log_level=log_level,
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        )
