from __future__ import annotations

from typing import Any


try:
    from opentelemetry import metrics
except Exception:  # pragma: no cover - dependency fallback
    metrics = None


class _NoOpInstrument:
    def add(self, *_args, **_kwargs) -> None:
        return None

    def record(self, *_args, **_kwargs) -> None:
        return None


def _instrument(factory, *args, **kwargs):
    if factory is None:
        return _NoOpInstrument()
    try:
        return factory(*args, **kwargs)
    except Exception:
        return _NoOpInstrument()


class ObservabilityMetrics:
    def __init__(self) -> None:
        meter = (
            metrics.get_meter("policyengine-household-api")
            if metrics
            else None
        )
        self.http_duration = _instrument(
            getattr(meter, "create_histogram", None),
            "http.server.request.duration",
            unit="s",
            description="HTTP server request duration.",
        )
        self.segment_duration = _instrument(
            getattr(meter, "create_histogram", None),
            "policyengine.household.segment.duration",
            unit="s",
            description="Household API request segment duration.",
        )
        self.calculate_duration = _instrument(
            getattr(meter, "create_histogram", None),
            "policyengine.household.calculate.duration",
            unit="s",
            description="Household calculate endpoint duration.",
        )
        self.backend_duration = _instrument(
            getattr(meter, "create_histogram", None),
            "policyengine.household.backend.duration",
            unit="s",
            description="Gateway backend call duration.",
        )
        self.requests = _instrument(
            getattr(meter, "create_counter", None),
            "policyengine.household.requests",
            description="Household API request count.",
        )
        self.errors = _instrument(
            getattr(meter, "create_counter", None),
            "policyengine.household.errors",
            description="Household API error count.",
        )
        self.rate_limited = _instrument(
            getattr(meter, "create_counter", None),
            "policyengine.household.rate_limited_requests",
            description="Household API rate-limited request count.",
        )
        self.failover_events = _instrument(
            getattr(meter, "create_counter", None),
            "policyengine.household.failover.events",
            description="Household API failover event count.",
        )
        self.active_requests = _instrument(
            getattr(meter, "create_up_down_counter", None),
            "http.server.active_requests",
            description="Active HTTP server requests.",
        )

    def record_request(
        self,
        duration_seconds: float,
        attributes: dict[str, Any],
    ) -> None:
        self.http_duration.record(duration_seconds, attributes)
        self.requests.add(1, attributes)

    def record_segment(
        self,
        segment: str,
        duration_seconds: float,
        attributes: dict[str, Any],
    ) -> None:
        segment_attributes = {**attributes, "segment": segment}
        self.segment_duration.record(duration_seconds, segment_attributes)
        if segment == "calculation":
            self.calculate_duration.record(duration_seconds, attributes)
        if segment in {
            "modal_request",
            "cloud_run_request",
            "worker_dispatch",
        }:
            self.backend_duration.record(duration_seconds, segment_attributes)

    def record_error(self, attributes: dict[str, Any]) -> None:
        self.errors.add(1, attributes)

    def record_rate_limited(self, attributes: dict[str, Any]) -> None:
        self.rate_limited.add(1, attributes)

    def record_failover_event(self, attributes: dict[str, Any]) -> None:
        self.failover_events.add(1, attributes)

    def add_active_request(
        self, delta: int, attributes: dict[str, Any]
    ) -> None:
        self.active_requests.add(delta, attributes)


METRICS = ObservabilityMetrics()
