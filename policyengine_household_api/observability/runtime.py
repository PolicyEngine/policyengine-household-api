from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import sys
import time
import traceback
import uuid
from typing import Any, Iterator

from flask import Flask, g, has_request_context, request

from .config import ObservabilityConfig
from .internal import PlainMessageFormatter
from .segments import SegmentName
from .segments import coerce_segment_name


OBSERVABILITY_INTERNAL_DISPATCH_HEADER = "X-PolicyEngine-Internal-Dispatch"
REQUEST_ID_HEADER = "X-PolicyEngine-Request-Id"
TRACEPARENT_HEADER = "traceparent"

REQUEST_LOGGER_NAME = "policyengine_household_api.observability.requests"
EVENT_LOGGER_NAME = "policyengine_household_api.observability.events"
INTERNAL_LOGGER_NAME = "policyengine_household_api.observability.internal"

REQUEST_LOGGER = logging.getLogger(REQUEST_LOGGER_NAME)
EVENT_LOGGER = logging.getLogger(EVENT_LOGGER_NAME)
INTERNAL_LOGGER = logging.getLogger(INTERNAL_LOGGER_NAME)

METRIC_ATTRIBUTE_KEYS = (
    "service.name",
    "service.role",
    "deployment.environment",
    "route",
    "method",
    "endpoint",
    "status_code",
    "country_id",
    "backend",
    "requested_version",
    "resolved_channel",
    "auth_result",
    "segment",
    "event",
    "error_type",
)


class _NoOpInstrument:
    def add(self, *_args, **_kwargs) -> None:
        return None

    def record(self, *_args, **_kwargs) -> None:
        return None


@dataclass
class ErrorRecord:
    type: str
    message: str
    handled: bool
    stack: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "handled": self.handled,
            "stack": self.stack,
        }


@dataclass
class RequestObservabilityContext:
    config: ObservabilityConfig
    request_id: str
    method: str
    route: str
    path: str
    endpoint: str | None
    query_keys: list[str]
    content_length_bytes: int | None
    inbound: dict[str, Any]
    internal_dispatch: bool = False
    started_at: float = field(default_factory=time.perf_counter)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    attributes: dict[str, Any] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)
    status_code: int | None = None
    error: ErrorRecord | None = None
    emitted: bool = False
    active_closed: bool = False
    span_closed: bool = False
    server_span_cm: Any = None
    server_span: Any = None

    def set_attribute(self, key: str, value: Any) -> None:
        if value is None:
            return
        if hasattr(value, "value"):
            value = value.value
        self.attributes[key] = value

    def duration_seconds(self) -> float:
        return time.perf_counter() - self.started_at

    def metric_attributes(self, **extra: Any) -> dict[str, str]:
        attrs: dict[str, Any] = {
            "service.name": self.config.service_name,
            "service.role": self.config.service_role,
            "deployment.environment": self.config.environment,
            "route": self.route,
            "method": self.method,
            "endpoint": self.endpoint,
        }
        if self.status_code is not None:
            attrs["status_code"] = str(self.status_code)
        for key in (
            "country_id",
            "backend",
            "requested_version",
            "resolved_channel",
            "auth_result",
        ):
            if key in self.attributes:
                attrs[key] = self.attributes[key]
        attrs.update(extra)
        return _metric_attrs(attrs)

    def span_attributes(self, **extra: Any) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "service.name": self.config.service_name,
            "service.role": self.config.service_role,
            "deployment.environment": self.config.environment,
            "http.request.method": self.method,
            "http.route": self.route,
            "url.path": self.path,
            "policyengine.endpoint": self.endpoint,
            "policyengine.request_id": self.request_id,
        }
        if self.status_code is not None:
            attrs["http.response.status_code"] = self.status_code
        for key in (
            "country_id",
            "backend",
            "requested_version",
            "resolved_channel",
            "auth_result",
        ):
            if key in self.attributes:
                attrs[f"policyengine.{key}"] = self.attributes[key]
        attrs.update(extra)
        return {
            key: value for key, value in attrs.items() if value is not None
        }

    def as_log_record(
        self,
        *,
        trace_id: str | None,
        span_id: str | None,
    ) -> dict[str, Any]:
        event = (
            "http_request_failed" if self.error else "http_request_completed"
        )
        status_code = self.status_code or (500 if self.error else None)
        return {
            "schema_version": "policyengine.observability.request.v1",
            "event": event,
            "service_name": self.config.service_name,
            "service_role": self.config.service_role,
            "environment": self.config.environment,
            "created_at": self.created_at.isoformat(),
            "request_id": self.request_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "method": self.method,
            "route": self.route,
            "path": self.path,
            "query_keys": self.query_keys,
            "endpoint": self.endpoint,
            "status_code": status_code,
            "duration_ms": round(self.duration_seconds() * 1000, 3),
            **self.inbound,
            "timings_ms": dict(self.timings_ms),
            **self.attributes,
            "error": self.error.as_dict() if self.error else None,
        }


class ObservabilityRuntime:
    def __init__(self, config: ObservabilityConfig) -> None:
        self.config = config
        self.enabled = config.enabled
        self.trace = None
        self.propagate = None
        self.SpanKind = None
        self.Status = None
        self.StatusCode = None
        self.tracer = None
        self.meter = None
        self.http_duration = _NoOpInstrument()
        self.segment_duration = _NoOpInstrument()
        self.calculate_duration = _NoOpInstrument()
        self.backend_duration = _NoOpInstrument()
        self.requests = _NoOpInstrument()
        self.errors = _NoOpInstrument()
        self.rate_limited = _NoOpInstrument()
        self.failover_events = _NoOpInstrument()
        self.active_requests = _NoOpInstrument()

    @classmethod
    def disabled(cls) -> "ObservabilityRuntime":
        return cls(ObservabilityConfig(enabled=False))

    def configure(self) -> None:
        self._configure_loggers()
        if not self.enabled:
            return
        self._configure_otel()

    def instrument_flask(self, app: Flask) -> None:
        if not self.enabled:
            return

        @app.before_request
        def _start_observed_request() -> None:
            self.start_request()

        @app.after_request
        def _finish_observed_request(response):
            self.finish_request(response)
            return response

        @app.teardown_request
        def _emit_observed_request(exc) -> None:
            self.teardown_request(exc)

    def current_context(self) -> RequestObservabilityContext | None:
        if not has_request_context():
            return None
        return getattr(g, "observability_context", None)

    def set_attribute(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        try:
            context = self.current_context()
            if context is not None:
                context.set_attribute(key, value)
                self._set_current_span_attributes(
                    context.span_attributes(**{f"policyengine.{key}": value})
                )
        except BaseException as exc:
            self.log_observability_failure(
                "request.set_attribute",
                exc,
                attribute=key,
            )

    @contextmanager
    def segment(
        self, name: SegmentName | str | Any, **attrs: Any
    ) -> Iterator[None]:
        if not self.enabled:
            yield
            return

        segment_name, is_registered = coerce_segment_name(name)
        if not is_registered:
            self.log_observability_failure(
                "segment.coerce",
                ValueError("Unregistered observability segment."),
                segment=segment_name,
                segment_type=type(name).__name__,
            )

        start = self._safe_perf_counter(f"segment.{segment_name}.start")
        span_attrs = self._segment_span_attributes(attrs)
        with self._safe_span(f"household.{segment_name}", span_attrs):
            try:
                yield
            except BaseException:
                self._record_segment_safely(segment_name, start, attrs)
                raise
            else:
                self._record_segment_safely(segment_name, start, attrs)

    def record_error(
        self,
        exc: BaseException,
        *,
        handled: bool,
        status_code: int | None = None,
        include_stack: bool = True,
    ) -> None:
        if not self.enabled:
            return
        try:
            context = self.current_context()
            if context is None:
                return
            if status_code is not None:
                context.status_code = status_code
            context.error = ErrorRecord(
                type=type(exc).__name__,
                message=self._safe_str(exc),
                handled=handled,
                stack=(self._safe_traceback(exc) if include_stack else None),
            )
            self.record_error_metric(
                context.metric_attributes(error_type=type(exc).__name__)
            )
            span = self._current_span()
            if span is not None:
                self._record_exception_on_span(
                    span,
                    exc,
                    handled=handled,
                    status_code=status_code,
                )
        except BaseException as observability_exc:
            self.log_observability_failure(
                "request.record_error",
                observability_exc,
                original_error_type=type(exc).__name__,
            )

    def record_event(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        try:
            context = self.current_context()
            base: dict[str, Any] = {
                "schema_version": "policyengine.observability.event.v1",
                "event": event,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if context is not None:
                trace_id, span_id = self._trace_ids()
                base.update(
                    {
                        "service_name": context.config.service_name,
                        "service_role": context.config.service_role,
                        "environment": context.config.environment,
                        "request_id": context.request_id,
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "route": context.route,
                        "path": context.path,
                    }
                )
            clean_fields = {
                key: value
                for key, value in fields.items()
                if value is not None
            }
            base.update(clean_fields)
            EVENT_LOGGER.info(self._json(base))
            self._add_span_event(event, clean_fields)
            if event.startswith("modal_") or "fallback" in event:
                attrs = (
                    context.metric_attributes(event=event)
                    if context
                    else _metric_attrs({"event": event})
                )
                self.record_failover_event_metric(attrs)
        except BaseException as exc:
            self.log_observability_failure(
                "request.record_event",
                exc,
                event_name=event,
            )

    def traceparent_header(self) -> str | None:
        if not self.enabled or self.propagate is None:
            return None
        try:
            carrier: dict[str, str] = {}
            self.propagate.inject(carrier)
            return carrier.get(TRACEPARENT_HEADER)
        except BaseException as exc:
            self.log_observability_failure("request.traceparent_header", exc)
            return None

    def start_request(self) -> None:
        if not self.enabled:
            return
        try:
            route = request.url_rule.rule if request.url_rule else request.path
            request_id = request.headers.get(REQUEST_ID_HEADER) or str(
                uuid.uuid4()
            )
            context = RequestObservabilityContext(
                config=self.config,
                request_id=request_id,
                method=request.method,
                route=route,
                path=request.path,
                endpoint=request.endpoint,
                query_keys=sorted(request.args.keys()),
                content_length_bytes=request.content_length,
                inbound=self._inbound_request_metadata(),
                internal_dispatch=(
                    request.headers.get(OBSERVABILITY_INTERNAL_DISPATCH_HEADER)
                    == "1"
                ),
            )
            g.observability_context = context
            context.set_attribute("endpoint", request.endpoint)
            self._start_request_span(context)
            self.record_active_request(1, context.metric_attributes())
        except BaseException as exc:
            self.log_observability_failure("flask.before_request", exc)

    def finish_request(self, response) -> None:
        if not self.enabled:
            return
        try:
            context = self.current_context()
            if context is None:
                return
            context.status_code = response.status_code
            self._set_current_span_attributes(context.span_attributes())
            response.headers[REQUEST_ID_HEADER] = context.request_id
            traceparent = self.traceparent_header()
            if traceparent:
                response.headers[TRACEPARENT_HEADER] = traceparent
            if response.status_code == 429:
                context.set_attribute("rate_limited", True)
                self.record_rate_limited_metric(context.metric_attributes())
            self.record_request_metric(
                context.duration_seconds(),
                context.metric_attributes(),
            )
            self._close_active_request(context)
        except BaseException as exc:
            self.log_observability_failure("flask.after_request", exc)

    def teardown_request(self, exc: BaseException | None) -> None:
        if not self.enabled:
            return
        context = self.current_context()
        if context is None:
            return
        try:
            if exc is not None:
                self.record_error(exc, handled=False, status_code=500)
            self._close_active_request(context)
            self.emit_request_log(context)
        except BaseException as observability_exc:
            self.log_observability_failure(
                "flask.teardown_request",
                observability_exc,
            )
        finally:
            self._close_request_span(context, exc)

    def emit_request_log(self, context: RequestObservabilityContext) -> None:
        if not self.enabled:
            return
        try:
            if context.emitted:
                return
            context.emitted = True
            if (
                context.internal_dispatch
                or not context.config.request_logs_enabled
            ):
                return
            trace_id, span_id = self._trace_ids()
            REQUEST_LOGGER.info(
                self._json(
                    context.as_log_record(
                        trace_id=trace_id,
                        span_id=span_id,
                    )
                )
            )
        except BaseException as exc:
            self.log_observability_failure(
                "request.emit_request_log",
                exc,
                request_id=getattr(context, "request_id", None),
            )

    def record_request_metric(
        self,
        duration_seconds: float,
        attributes: dict[str, str],
    ) -> None:
        try:
            self.http_duration.record(duration_seconds, attributes)
            self.requests.add(1, attributes)
        except BaseException as exc:
            self.log_observability_failure("metrics.record_request", exc)

    def record_segment_metric(
        self,
        segment: str,
        duration_seconds: float,
        attributes: dict[str, str],
        *,
        backend_segment: bool = False,
    ) -> None:
        try:
            segment_attributes = {**attributes, "segment": segment}
            self.segment_duration.record(duration_seconds, segment_attributes)
            if segment == "calculation":
                self.calculate_duration.record(duration_seconds, attributes)
            if backend_segment:
                self.backend_duration.record(
                    duration_seconds, segment_attributes
                )
        except BaseException as exc:
            self.log_observability_failure(
                "metrics.record_segment",
                exc,
                segment=segment,
            )

    def record_error_metric(self, attributes: dict[str, str]) -> None:
        try:
            self.errors.add(1, attributes)
        except BaseException as exc:
            self.log_observability_failure("metrics.record_error", exc)

    def record_rate_limited_metric(self, attributes: dict[str, str]) -> None:
        try:
            self.rate_limited.add(1, attributes)
        except BaseException as exc:
            self.log_observability_failure("metrics.record_rate_limited", exc)

    def record_failover_event_metric(self, attributes: dict[str, str]) -> None:
        try:
            self.failover_events.add(1, attributes)
        except BaseException as exc:
            self.log_observability_failure(
                "metrics.record_failover_event", exc
            )

    def record_active_request(
        self,
        delta: int,
        attributes: dict[str, str],
    ) -> None:
        try:
            self.active_requests.add(delta, attributes)
        except BaseException as exc:
            self.log_observability_failure("metrics.add_active_request", exc)

    def log_observability_failure(
        self,
        operation: str,
        exc: BaseException,
        **fields: Any,
    ) -> None:
        try:
            payload = {
                "schema_version": "policyengine.observability.internal_error.v1",
                "event": "observability_internal_error",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
                "error": {
                    "type": type(exc).__name__,
                    "message": self._safe_str(exc),
                    "stack": self._safe_traceback(exc),
                },
            }
            payload.update(
                {
                    key: value
                    for key, value in fields.items()
                    if value is not None
                }
            )
            INTERNAL_LOGGER.error(self._json(payload))
        except BaseException:
            self._write_stderr(payload)

    def _configure_loggers(self) -> None:
        for logger in (REQUEST_LOGGER, EVENT_LOGGER, INTERNAL_LOGGER):
            logger.setLevel(self.config.log_level)
            logger.propagate = False
            if not logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(PlainMessageFormatter())
                logger.addHandler(handler)

    def _configure_otel(self) -> None:
        try:
            from opentelemetry import metrics
            from opentelemetry import propagate
            from opentelemetry import trace
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT
            from opentelemetry.sdk.resources import SERVICE_NAME
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.trace import SpanKind
            from opentelemetry.trace import Status
            from opentelemetry.trace import StatusCode
        except BaseException as exc:
            self.log_observability_failure("otel.configure_imports", exc)
            return

        try:
            resource = Resource.create(
                {
                    SERVICE_NAME: self.config.service_name,
                    DEPLOYMENT_ENVIRONMENT: self.config.environment,
                    "service.role": self.config.service_role,
                }
            )
            tracer_provider = TracerProvider(resource=resource)
            metric_readers = []
            if self.config.otlp_endpoint:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter,
                )
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                from opentelemetry.sdk.metrics.export import (
                    PeriodicExportingMetricReader,
                )
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                tracer_provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter())
                )
                metric_readers.append(
                    PeriodicExportingMetricReader(OTLPMetricExporter())
                )
            try:
                trace.set_tracer_provider(tracer_provider)
            except BaseException as exc:
                self.log_observability_failure(
                    "otel.set_tracer_provider",
                    exc,
                )
            try:
                metrics.set_meter_provider(
                    MeterProvider(
                        resource=resource,
                        metric_readers=metric_readers,
                    )
                )
            except BaseException as exc:
                self.log_observability_failure(
                    "otel.set_meter_provider",
                    exc,
                )
            self.trace = trace
            self.propagate = propagate
            self.SpanKind = SpanKind
            self.Status = Status
            self.StatusCode = StatusCode
            self.tracer = trace.get_tracer("policyengine-household-api")
            self.meter = metrics.get_meter("policyengine-household-api")
            self._configure_instruments()
        except BaseException as exc:
            self.log_observability_failure("otel.configure", exc)

    def _configure_instruments(self) -> None:
        self.http_duration = self._instrument(
            getattr(self.meter, "create_histogram", None),
            "http.server.request.duration",
            unit="s",
            description="HTTP server request duration.",
        )
        self.segment_duration = self._instrument(
            getattr(self.meter, "create_histogram", None),
            "policyengine.household.segment.duration",
            unit="s",
            description="Household API request segment duration.",
        )
        self.calculate_duration = self._instrument(
            getattr(self.meter, "create_histogram", None),
            "policyengine.household.calculate.duration",
            unit="s",
            description="Household calculate endpoint duration.",
        )
        self.backend_duration = self._instrument(
            getattr(self.meter, "create_histogram", None),
            "policyengine.household.backend.duration",
            unit="s",
            description="Gateway backend call duration.",
        )
        self.requests = self._instrument(
            getattr(self.meter, "create_counter", None),
            "policyengine.household.requests",
            description="Household API request count.",
        )
        self.errors = self._instrument(
            getattr(self.meter, "create_counter", None),
            "policyengine.household.errors",
            description="Household API error count.",
        )
        self.rate_limited = self._instrument(
            getattr(self.meter, "create_counter", None),
            "policyengine.household.rate_limited_requests",
            description="Household API rate-limited request count.",
        )
        self.failover_events = self._instrument(
            getattr(self.meter, "create_counter", None),
            "policyengine.household.failover.events",
            description="Household API failover event count.",
        )
        self.active_requests = self._instrument(
            getattr(self.meter, "create_up_down_counter", None),
            "http.server.active_requests",
            description="Active HTTP server requests.",
        )

    def _instrument(self, factory, *args, **kwargs):
        if factory is None:
            return _NoOpInstrument()
        try:
            return factory(*args, **kwargs)
        except BaseException as exc:
            self.log_observability_failure(
                "metrics.create_instrument",
                exc,
                instrument=args[0] if args else None,
            )
            return _NoOpInstrument()

    def _start_request_span(
        self,
        context: RequestObservabilityContext,
    ) -> None:
        if self.tracer is None:
            return
        attrs = context.span_attributes()
        parent_context = self._extract_context()
        try:
            context.server_span_cm = self.tracer.start_as_current_span(
                context.route,
                context=parent_context,
                kind=self.SpanKind.SERVER if self.SpanKind else None,
                attributes=attrs,
            )
            context.server_span = context.server_span_cm.__enter__()
        except BaseException as exc:
            context.server_span_cm = None
            context.server_span = None
            self.log_observability_failure("otel.request_span_enter", exc)

    def _close_request_span(
        self,
        context: RequestObservabilityContext,
        exc: BaseException | None,
    ) -> None:
        if context.span_closed:
            return
        context.span_closed = True
        span_cm = context.server_span_cm
        if span_cm is None:
            return
        try:
            if exc is None:
                span_cm.__exit__(None, None, None)
            else:
                span_cm.__exit__(type(exc), exc, exc.__traceback__)
        except BaseException as observability_exc:
            self.log_observability_failure(
                "otel.request_span_exit",
                observability_exc,
                request_id=context.request_id,
            )

    @contextmanager
    def _safe_span(self, name: str, attrs: dict[str, Any]) -> Iterator[None]:
        if self.tracer is None:
            yield
            return
        span_cm = None
        try:
            span_cm = self.tracer.start_as_current_span(
                name,
                attributes=attrs,
            )
            span_cm.__enter__()
        except BaseException as exc:
            self.log_observability_failure("otel.span_enter", exc, span=name)
            yield
            return

        try:
            yield
        except BaseException:
            exc_type, exc, tb = self._current_exception()
            try:
                span_cm.__exit__(exc_type, exc, tb)
            except BaseException as observability_exc:
                self.log_observability_failure(
                    "otel.span_exit",
                    observability_exc,
                    span=name,
                )
            raise
        else:
            try:
                span_cm.__exit__(None, None, None)
            except BaseException as exc:
                self.log_observability_failure(
                    "otel.span_exit", exc, span=name
                )

    def _record_segment_safely(
        self,
        name: str,
        start: float | None,
        attrs: dict[str, Any],
    ) -> None:
        if start is None:
            return
        end = self._safe_perf_counter(f"segment.{name}.end")
        if end is None:
            return
        try:
            context = self.current_context()
            duration = end - start
            if context is not None:
                context.timings_ms[name] = round(duration * 1000, 3)
                metric_extra = {
                    key: value
                    for key, value in attrs.items()
                    if key in METRIC_ATTRIBUTE_KEYS and value is not None
                }
                self.record_segment_metric(
                    name,
                    duration,
                    context.metric_attributes(
                        segment=name,
                        **metric_extra,
                    ),
                    backend_segment="backend" in metric_extra,
                )
        except BaseException as exc:
            self.log_observability_failure(
                "request.record_segment",
                exc,
                segment=name,
            )

    def _segment_span_attributes(
        self, attrs: dict[str, Any]
    ) -> dict[str, Any]:
        context = self.current_context()
        span_attrs = {
            key: value for key, value in attrs.items() if value is not None
        }
        if context is not None:
            span_attrs = {**context.span_attributes(), **span_attrs}
        return span_attrs

    def _set_current_span_attributes(self, attrs: dict[str, Any]) -> None:
        span = self._current_span()
        if span is None:
            return
        try:
            for key, value in attrs.items():
                if value is not None:
                    span.set_attribute(key, value)
        except BaseException as exc:
            self.log_observability_failure("otel.set_span_attributes", exc)

    def _current_span(self):
        if self.trace is None:
            return None
        try:
            return self.trace.get_current_span()
        except BaseException as exc:
            self.log_observability_failure("otel.current_span", exc)
            return None

    def _trace_ids(self) -> tuple[str | None, str | None]:
        span = self._current_span()
        if span is None:
            return None, None
        try:
            context = span.get_span_context()
        except BaseException as exc:
            self.log_observability_failure("otel.span_context", exc)
            return None, None
        if not getattr(context, "is_valid", False):
            return None, None
        return f"{context.trace_id:032x}", f"{context.span_id:016x}"

    def _extract_context(self):
        if self.propagate is None:
            return None
        try:
            return self.propagate.extract(request.headers)
        except BaseException as exc:
            self.log_observability_failure("otel.extract_context", exc)
            return None

    def _record_exception_on_span(
        self,
        span,
        exc: BaseException,
        *,
        handled: bool,
        status_code: int | None,
    ) -> None:
        try:
            span.record_exception(exc)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.handled", handled)
            if (
                self.Status is not None
                and self.StatusCode is not None
                and (
                    not handled
                    or (status_code is not None and status_code >= 500)
                )
            ):
                span.set_status(
                    self.Status(
                        self.StatusCode.ERROR,
                        self._safe_str(exc),
                    )
                )
        except BaseException as observability_exc:
            self.log_observability_failure(
                "otel.record_exception",
                observability_exc,
                original_error_type=type(exc).__name__,
            )

    def _add_span_event(self, event: str, fields: dict[str, Any]) -> None:
        span = self._current_span()
        if span is None:
            return
        try:
            span.add_event(
                event,
                {
                    key: value
                    for key, value in fields.items()
                    if _is_safe_span_value(value)
                },
            )
        except BaseException as exc:
            self.log_observability_failure(
                "otel.add_event",
                exc,
                event_name=event,
            )

    def _close_active_request(
        self,
        context: RequestObservabilityContext,
    ) -> None:
        try:
            if context.active_closed:
                return
            context.active_closed = True
            self.record_active_request(-1, context.metric_attributes())
        except BaseException as exc:
            self.log_observability_failure(
                "flask.close_active_request",
                exc,
                request_id=getattr(context, "request_id", None),
            )

    def _inbound_request_metadata(self) -> dict:
        forwarded_for = _split_forwarded_for(
            request.headers.get("X-Forwarded-For")
        )
        x_real_ip = request.headers.get("X-Real-IP")
        remote_addr = request.remote_addr

        client_ip = None
        ip_source = None
        if forwarded_for:
            client_ip = forwarded_for[0]
            ip_source = "x_forwarded_for"
        elif x_real_ip:
            client_ip = x_real_ip
            ip_source = "x_real_ip"
        elif remote_addr:
            client_ip = remote_addr
            ip_source = "remote_addr"

        metadata = {
            "ip_source": ip_source,
            "user_agent": request.headers.get("User-Agent"),
            "origin": request.headers.get("Origin"),
            "referer": request.headers.get("Referer"),
            "host": request.host,
            "content_length_bytes": request.content_length,
        }
        if self.config.log_raw_ip:
            metadata["client_ip"] = client_ip
            metadata["forwarded_for"] = forwarded_for
            metadata["x_real_ip"] = x_real_ip
        return metadata

    def _safe_perf_counter(self, operation: str) -> float | None:
        try:
            return time.perf_counter()
        except BaseException as exc:
            self.log_observability_failure(operation, exc)
            return None

    def _safe_str(self, value: Any) -> str:
        try:
            return str(value)
        except BaseException:
            return f"<unprintable {type(value).__name__}>"

    def _safe_traceback(self, exc: BaseException) -> str:
        try:
            return "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        except BaseException:
            return ""

    def _json(self, payload: dict[str, Any]) -> str:
        try:
            return json.dumps(payload, sort_keys=True, default=str)
        except BaseException:
            return json.dumps(
                {
                    "schema_version": "policyengine.observability.internal_error.v1",
                    "event": "observability_internal_error",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "operation": "observability.failure_json",
                },
                sort_keys=True,
            )

    def _write_stderr(self, payload: dict[str, Any]) -> None:
        try:
            sys.stderr.write(self._json(payload) + "\n")
        except BaseException:
            return

    def _current_exception(self):
        return sys.exc_info()


_RUNTIME = ObservabilityRuntime.disabled()


def set_observability_runtime(runtime: ObservabilityRuntime) -> None:
    global _RUNTIME
    _RUNTIME = runtime


def observability_runtime() -> ObservabilityRuntime:
    return _RUNTIME


def _metric_attrs(attrs: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in METRIC_ATTRIBUTE_KEYS:
        value = attrs.get(key)
        if value is not None:
            result[key] = str(value)
    return result


def _is_safe_span_value(value: Any) -> bool:
    return isinstance(value, str | bool | int | float)


def _split_forwarded_for(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
