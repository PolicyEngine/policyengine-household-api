from __future__ import annotations

from policyengine_observability.context import ErrorRecord
from policyengine_observability.context import METRIC_ATTRIBUTE_KEYS
from policyengine_observability.context import RequestObservabilityContext
from policyengine_observability.runtime import (
    EVENT_LOGGER,
    EVENT_LOGGER_NAME,
    INTERNAL_LOGGER,
    INTERNAL_LOGGER_NAME,
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    REQUEST_LOGGER,
    REQUEST_LOGGER_NAME,
    TRACEPARENT_HEADER,
)
from policyengine_observability.runtime import (
    ObservabilityRuntime as BaseObservabilityRuntime,
)
from policyengine_observability.runtime import observability_runtime
from policyengine_observability.runtime import set_observability_runtime

from .config import ObservabilityConfig
from .segments import SegmentName


class ObservabilityRuntime(BaseObservabilityRuntime):
    def __init__(self, config: ObservabilityConfig) -> None:
        super().__init__(config, segment_registry=SegmentName)

    @classmethod
    def disabled(cls) -> "ObservabilityRuntime":
        return cls(ObservabilityConfig(enabled=False))


set_observability_runtime(ObservabilityRuntime.disabled())


__all__ = [
    "EVENT_LOGGER",
    "EVENT_LOGGER_NAME",
    "ErrorRecord",
    "INTERNAL_LOGGER",
    "INTERNAL_LOGGER_NAME",
    "METRIC_ATTRIBUTE_KEYS",
    "OBSERVABILITY_INTERNAL_DISPATCH_HEADER",
    "ObservabilityRuntime",
    "REQUEST_ID_HEADER",
    "REQUEST_LOGGER",
    "REQUEST_LOGGER_NAME",
    "RequestObservabilityContext",
    "TRACEPARENT_HEADER",
    "observability_runtime",
    "set_observability_runtime",
]
