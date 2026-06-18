from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import sys
import time
import traceback
from typing import Any, Iterator

from flask import g, has_request_context

from .config import ObservabilityConfig
from .internal import PlainMessageFormatter
from .internal import configure_internal_logger
from .internal import log_observability_failure
from .metrics import METRICS


try:
    from opentelemetry import trace
except BaseException:  # pragma: no cover - dependency fallback
    trace = None


OBSERVABILITY_INTERNAL_DISPATCH_HEADER = "X-PolicyEngine-Internal-Dispatch"
REQUEST_ID_HEADER = "X-PolicyEngine-Request-Id"
TRACEPARENT_HEADER = "traceparent"

REQUEST_LOGGER_NAME = "policyengine_household_api.observability.requests"
EVENT_LOGGER_NAME = "policyengine_household_api.observability.events"

_REQUEST_LOGGER = logging.getLogger(REQUEST_LOGGER_NAME)
_EVENT_LOGGER = logging.getLogger(EVENT_LOGGER_NAME)


def configure_json_loggers(config: ObservabilityConfig) -> None:
    configure_internal_logger(config.log_level)
    for logger in (_REQUEST_LOGGER, _EVENT_LOGGER):
        logger.setLevel(config.log_level)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(PlainMessageFormatter())
            logger.addHandler(handler)


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

    def set_attribute(self, key: str, value: Any) -> None:
        if value is None:
            return
        if hasattr(value, "value"):
            value = value.value
        self.attributes[key] = value

    def record_segment(self, name: str, duration_seconds: float) -> None:
        self.timings_ms[name] = round(duration_seconds * 1000, 3)
        METRICS.record_segment(
            name,
            duration_seconds,
            self.metric_attributes(),
        )

    def record_error(
        self,
        exc: BaseException,
        *,
        handled: bool,
        status_code: int | None = None,
        include_stack: bool = True,
    ) -> None:
        if status_code is not None:
            self.status_code = status_code
        self.error = ErrorRecord(
            type=type(exc).__name__,
            message=str(exc),
            handled=handled,
            stack=(
                "".join(
                    traceback.format_exception(
                        type(exc),
                        exc,
                        exc.__traceback__,
                    )
                )
                if include_stack
                else None
            ),
        )
        METRICS.record_error(
            self.metric_attributes(error_type=type(exc).__name__)
        )
        span = _current_span()
        if span is not None:
            try:
                span.record_exception(exc)
                span.set_attribute("error.type", type(exc).__name__)
            except BaseException as observability_exc:
                log_observability_failure(
                    "otel.record_exception",
                    observability_exc,
                    original_error_type=type(exc).__name__,
                )

    def duration_seconds(self) -> float:
        return time.perf_counter() - self.started_at

    def metric_attributes(self, **extra: Any) -> dict[str, Any]:
        status_code = self.status_code
        attributes = {
            "service.name": self.config.service_name,
            "service.role": self.config.service_role,
            "deployment.environment": self.config.environment,
            "route": self.route,
            "method": self.method,
        }
        if status_code is not None:
            attributes["status_code"] = str(status_code)
        for key in (
            "country_id",
            "backend",
            "requested_version",
            "resolved_channel",
            "auth_result",
        ):
            if key in self.attributes:
                attributes[key] = str(self.attributes[key])
        for key, value in extra.items():
            if value is not None:
                attributes[key] = str(value)
        return attributes

    def as_log_record(self) -> dict[str, Any]:
        event = (
            "http_request_failed" if self.error else "http_request_completed"
        )
        status_code = self.status_code or (500 if self.error else None)
        trace_id, span_id = _trace_ids()
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


def current_context() -> RequestObservabilityContext | None:
    if not has_request_context():
        return None
    return getattr(g, "observability_context", None)


def set_current_context(context: RequestObservabilityContext) -> None:
    g.observability_context = context


def set_request_attribute(key: str, value: Any) -> None:
    try:
        context = current_context()
        if context is not None:
            context.set_attribute(key, value)
    except BaseException as exc:
        log_observability_failure(
            "request.set_attribute",
            exc,
            attribute=key,
        )


def record_error(
    exc: BaseException,
    *,
    handled: bool = True,
    status_code: int | None = None,
    include_stack: bool = True,
) -> None:
    try:
        context = current_context()
        if context is not None:
            context.record_error(
                exc,
                handled=handled,
                status_code=status_code,
                include_stack=include_stack,
            )
    except BaseException as observability_exc:
        log_observability_failure(
            "request.record_error",
            observability_exc,
            original_error_type=type(exc).__name__,
        )


def record_event(event: str, **fields: Any) -> None:
    try:
        context = current_context()
        base: dict[str, Any] = {
            "schema_version": "policyengine.observability.event.v1",
            "event": event,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if context is not None:
            trace_id, span_id = _trace_ids()
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
        base.update(
            {key: value for key, value in fields.items() if value is not None}
        )
        _EVENT_LOGGER.info(_json(base))
        if event.startswith("modal_") or "fallback" in event:
            attrs = (
                context.metric_attributes(event=event)
                if context
                else {"event": event}
            )
            METRICS.record_failover_event(attrs)
    except BaseException as exc:
        log_observability_failure(
            "request.record_event",
            exc,
            event_name=event,
        )


def current_traceparent_header() -> str | None:
    try:
        trace_id, span_id = _trace_ids()
        if trace_id is None or span_id is None:
            return None
        return f"00-{trace_id}-{span_id}-01"
    except BaseException as exc:
        log_observability_failure("request.current_traceparent_header", exc)
        return None


@contextmanager
def timed_segment(name: str, **attrs: Any) -> Iterator[None]:
    start = _safe_perf_counter(f"timed_segment.{name}.start")
    try:
        with _safe_span(f"household.{name}", attrs):
            yield
    except BaseException:
        _record_segment_safely(name, start)
        raise
    else:
        _record_segment_safely(name, start)


def emit_request_log(context: RequestObservabilityContext) -> None:
    try:
        if context.emitted:
            return
        context.emitted = True
        if (
            context.internal_dispatch
            or not context.config.request_logs_enabled
        ):
            return
        _REQUEST_LOGGER.info(_json(context.as_log_record()))
    except BaseException as exc:
        log_observability_failure(
            "request.emit_request_log",
            exc,
            request_id=getattr(context, "request_id", None),
        )


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def _current_span():
    if trace is None:
        return None
    try:
        return trace.get_current_span()
    except BaseException as exc:
        log_observability_failure("otel.current_span", exc)
        return None


def _trace_ids() -> tuple[str | None, str | None]:
    span = _current_span()
    if span is None:
        return None, None
    try:
        context = span.get_span_context()
    except BaseException as exc:
        log_observability_failure("otel.span_context", exc)
        return None, None
    if not getattr(context, "is_valid", False):
        return None, None
    return f"{context.trace_id:032x}", f"{context.span_id:016x}"


def _start_span(name: str, attrs: dict[str, Any]):
    if trace is None:
        return None
    try:
        tracer = trace.get_tracer("policyengine-household-api")
        span_attrs = {
            key: value for key, value in attrs.items() if value is not None
        }
        return tracer.start_as_current_span(name, attributes=span_attrs)
    except BaseException as exc:
        log_observability_failure("otel.start_span", exc, span=name)
        return None


@contextmanager
def _safe_span(name: str, attrs: dict[str, Any]) -> Iterator[None]:
    span_cm = _start_span(name, attrs)
    if span_cm is None:
        yield
        return

    try:
        span_cm.__enter__()
    except BaseException as exc:
        log_observability_failure("otel.span_enter", exc, span=name)
        yield
        return

    try:
        yield
    except BaseException:
        exc_type, exc, tb = sys.exc_info()
        try:
            span_cm.__exit__(exc_type, exc, tb)
        except BaseException as observability_exc:
            log_observability_failure(
                "otel.span_exit",
                observability_exc,
                span=name,
            )
        raise
    else:
        try:
            span_cm.__exit__(None, None, None)
        except BaseException as exc:
            log_observability_failure("otel.span_exit", exc, span=name)


def _record_segment_safely(name: str, start: float | None) -> None:
    if start is None:
        return
    end = _safe_perf_counter(f"timed_segment.{name}.end")
    if end is None:
        return
    try:
        context = current_context()
        if context is not None:
            context.record_segment(name, end - start)
    except BaseException as exc:
        log_observability_failure(
            "request.record_segment",
            exc,
            segment=name,
        )


def _safe_perf_counter(operation: str) -> float | None:
    try:
        return time.perf_counter()
    except BaseException as exc:
        log_observability_failure(operation, exc)
        return None
