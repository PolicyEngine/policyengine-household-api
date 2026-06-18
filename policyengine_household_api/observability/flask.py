from __future__ import annotations

import uuid

from flask import Flask, request

from .config import ObservabilityConfig
from .metrics import METRICS
from .request import (
    OBSERVABILITY_INTERNAL_DISPATCH_HEADER,
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    RequestObservabilityContext,
    configure_json_loggers,
    current_context,
    emit_request_log,
    record_error,
    set_current_context,
    set_request_attribute,
)


try:
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
except Exception:  # pragma: no cover - optional dependency fallback
    FlaskInstrumentor = None


try:
    from opentelemetry import trace
except Exception:  # pragma: no cover - optional dependency fallback
    trace = None


try:
    from opentelemetry import metrics
except Exception:  # pragma: no cover - optional dependency fallback
    metrics = None


_OTEL_CONFIGURED = False


def init_observability(app: Flask, *, service_role: str = "api") -> None:
    if app.extensions.get("policyengine_observability"):
        return

    config = ObservabilityConfig.from_env(service_role=service_role)
    app.extensions["policyengine_observability"] = config
    if not config.enabled:
        return

    configure_json_loggers(config)
    _configure_otel(config)
    _instrument_flask(app)

    @app.before_request
    def _start_observed_request() -> None:
        route = request.url_rule.rule if request.url_rule else request.path
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        context = RequestObservabilityContext(
            config=config,
            request_id=request_id,
            method=request.method,
            route=route,
            path=request.path,
            endpoint=request.endpoint,
            query_keys=sorted(request.args.keys()),
            content_length_bytes=request.content_length,
            inbound=_inbound_request_metadata(config),
            internal_dispatch=(
                request.headers.get(OBSERVABILITY_INTERNAL_DISPATCH_HEADER)
                == "1"
            ),
        )
        set_current_context(context)
        set_request_attribute("endpoint", request.endpoint)
        METRICS.add_active_request(1, context.metric_attributes())

    @app.after_request
    def _finish_observed_request(response):
        context = current_context()
        if context is None:
            return response

        context.status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = context.request_id
        traceparent = _traceparent_header()
        if traceparent:
            response.headers[TRACEPARENT_HEADER] = traceparent

        if response.status_code == 429:
            context.set_attribute("rate_limited", True)
            METRICS.record_rate_limited(context.metric_attributes())

        METRICS.record_request(
            context.duration_seconds(),
            context.metric_attributes(),
        )
        _close_active_request(context)
        return response

    @app.teardown_request
    def _emit_observed_request(exc) -> None:
        context = current_context()
        if context is None:
            return
        if exc is not None:
            record_error(exc, handled=False, status_code=500)
        _close_active_request(context)
        emit_request_log(context)


def _instrument_flask(app: Flask) -> None:
    if FlaskInstrumentor is None:
        return
    try:
        FlaskInstrumentor().instrument_app(app)
    except Exception:
        return


def _configure_otel(config: ObservabilityConfig) -> None:
    global _OTEL_CONFIGURED
    if _OTEL_CONFIGURED or not config.otlp_endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT
        from opentelemetry.sdk.resources import SERVICE_NAME
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return
    if trace is None or metrics is None:
        return

    resource = Resource.create(
        {
            SERVICE_NAME: config.service_name,
            DEPLOYMENT_ENVIRONMENT: config.environment,
            "service.role": config.service_role,
        }
    )
    try:
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter())
        )
        trace.set_tracer_provider(tracer_provider)

        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=[metric_reader])
        )
        _OTEL_CONFIGURED = True
    except Exception:
        return


def _close_active_request(context: RequestObservabilityContext) -> None:
    if context.active_closed:
        return
    context.active_closed = True
    METRICS.add_active_request(-1, context.metric_attributes())


def _inbound_request_metadata(config: ObservabilityConfig) -> dict:
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
    if config.log_raw_ip:
        metadata["client_ip"] = client_ip
        metadata["forwarded_for"] = forwarded_for
        metadata["x_real_ip"] = x_real_ip
    return metadata


def _split_forwarded_for(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _traceparent_header() -> str | None:
    if trace is None:
        return None
    try:
        span_context = trace.get_current_span().get_span_context()
    except Exception:
        return None
    if not getattr(span_context, "is_valid", False):
        return None
    return (
        f"00-{span_context.trace_id:032x}-"
        f"{span_context.span_id:016x}-01"
    )
