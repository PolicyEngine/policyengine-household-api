from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import os

from policyengine_observability import (
    ObservabilityConfig as BaseObservabilityConfig,
)

from policyengine_household_api.utils.config_loader import get_config_value


def _environment() -> str:
    return (
        os.getenv("OBSERVABILITY_ENVIRONMENT")
        or os.getenv("DEPLOYMENT_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or str(get_config_value("app.environment", "development"))
    )


@dataclass(frozen=True)
class ObservabilityConfig(BaseObservabilityConfig):
    service_name: str = "policyengine-household-api"
    service_role: str = "api"
    span_prefix: str | None = "household"

    @classmethod
    def from_env(cls, *, service_role: str) -> "ObservabilityConfig":
        base = BaseObservabilityConfig.from_env(
            service_name=cls.service_name,
            service_role=service_role,
            span_prefix=cls.span_prefix,
        )
        values = asdict(base)
        values["environment"] = _environment()
        return cls(**values)
