"""
Optional analytics decorator that enqueues analytics if analytics is enabled.
"""

from functools import wraps
from flask import g, request
from datetime import datetime, timezone
import logging
from policyengine_observability import segment
from policyengine_observability import set_attribute
from policyengine_household_api.analytics.cloud_tasks import (
    enqueue_calculate_analytics_event,
)
from policyengine_household_analytics.events import CalculateAnalyticsEvent
from policyengine_household_api.constants import VERSION
from policyengine_household_analytics.analytics_setup import (
    is_analytics_enabled,
)
from policyengine_household_common.models.analytics import (
    AnalyticsContext,
    ModalResolvedChannel,
    VariableUsageSummary,
)
from policyengine_household_common.observability.segments import SegmentName
from policyengine_household_common.routing_metadata import (
    REQUESTED_VERSION_ENVIRON_KEY,
    RESOLVED_CHANNEL_ENVIRON_KEY,
)
from policyengine_household_common.variable_usage_analytics import (
    extract_variable_usage,
)
from policyengine_household_common.config_loader import get_config_value

logger = logging.getLogger(__name__)


def log_analytics_if_enabled(func):
    """
    Decorator that enqueues analytics when enabled in configuration.

    Analytics is intentionally best-effort on the request path. If analytics is
    disabled, this passes through without logging. If analytics is enabled,
    context-building and Cloud Tasks enqueue failures are logged but do not
    change the wrapped endpoint response.
    """

    @wraps(func)
    def decorated_function(*args, **kwargs):
        try:
            analytics_enabled = is_analytics_enabled()
        except Exception:
            logger.warning(
                "Failed to determine whether analytics is enabled; "
                "continuing request without analytics.",
                exc_info=True,
            )
            return func(*args, **kwargs)

        if not analytics_enabled:
            return func(*args, **kwargs)

        analytics_context = _safe_build_analytics_context(args, kwargs)
        _safe_set_observability_context_attributes(analytics_context)

        try:
            response = func(*args, **kwargs)
        except Exception:
            _enqueue_analytics_best_effort(analytics_context, 500)
            raise

        _enqueue_analytics_best_effort(
            analytics_context,
            getattr(response, "status_code", None),
        )
        return response

    return decorated_function


def _safe_build_analytics_context(args, kwargs) -> AnalyticsContext | None:
    try:
        with segment(SegmentName.ANALYTICS_CONTEXT_BUILD):
            return _build_analytics_context(args, kwargs)
    except Exception:
        logger.warning(
            "Failed to build analytics context; continuing request without "
            "analytics.",
            exc_info=True,
        )
        return None


def _enqueue_analytics_best_effort(
    context: AnalyticsContext | None,
    response_status_code: int | None,
) -> None:
    if context is None:
        return

    try:
        with segment(SegmentName.ANALYTICS_WRITE):
            enqueue_calculate_analytics_event(
                CalculateAnalyticsEvent(
                    context=context,
                    response_status_code=response_status_code,
                )
            )
    except Exception:
        logger.warning(
            "Failed to enqueue calculate analytics event; continuing request "
            "without analytics.",
            exc_info=True,
        )


def _safe_set_observability_context_attributes(
    context: AnalyticsContext | None,
) -> None:
    try:
        _set_observability_context_attributes(context)
    except Exception:
        logger.warning(
            "Failed to attach analytics observability attributes; continuing "
            "request without analytics attributes.",
            exc_info=True,
        )


def _build_analytics_context(args, kwargs) -> AnalyticsContext:
    now = datetime.now(timezone.utc)
    client_id = _client_id_from_request()
    country_id = _country_id_from_route_args(args, kwargs)
    payload = _request_json()
    requested_version, resolved_channel = _routing_metadata_from_request()

    context = AnalyticsContext(
        client_id=client_id,
        api_version=VERSION,
        endpoint=request.endpoint,
        method=request.method,
        content_length_bytes=request.content_length,
        created_at=now,
        country_id=country_id,
        requested_version=requested_version,
        resolved_channel=resolved_channel,
    )

    if country_id is None or not _collect_variable_usage():
        return context

    from policyengine_household_api.country import COUNTRIES

    country = COUNTRIES.get(country_id)
    if country is None:
        return context
    variable_summaries: tuple[VariableUsageSummary, ...] = ()
    if isinstance(payload, dict):
        household = payload.get("household", {})
        if isinstance(household, dict):
            variable_summaries = tuple(
                extract_variable_usage(
                    household,
                    country.tax_benefit_system,
                )
            )

    return context.model_copy(
        update={
            "record_calculate_request": True,
            "model_version": country.policyengine_bundle.get("model_version"),
            "variable_summaries": variable_summaries,
        },
    )


def _client_id_from_request() -> str | None:
    # The auth decorator has already validated the bearer token and stored the
    # resulting token object on Flask's request context. Do not re-parse or
    # re-validate the raw Authorization header here.
    try:
        client_id = _sub_claim_from_validated_token()
    except Exception as e:
        logger.debug(f"Could not extract client_id from validated token: {e}")
        return None

    if client_id is None:
        return None

    suffix_to_slice = "@clients"
    if client_id.endswith(suffix_to_slice):
        return client_id[: -len(suffix_to_slice)]
    return client_id


def _sub_claim_from_validated_token() -> str | None:
    try:
        token = getattr(g, "authlib_server_oauth2_token", None)
    except RuntimeError:
        return None

    if token is None:
        return None

    if isinstance(token, dict):
        sub = token.get("sub")
    else:
        try:
            sub = token["sub"]
        except (KeyError, TypeError, AttributeError):
            sub = getattr(token, "sub", None)

    return sub if isinstance(sub, str) else None


def _country_id_from_route_args(args, kwargs) -> str | None:
    country_id = kwargs.get("country_id")
    if isinstance(country_id, str):
        return country_id
    if args and isinstance(args[0], str):
        return args[0]
    return None


def _request_json() -> dict | None:
    return request.get_json(silent=True)


def _collect_variable_usage() -> bool:
    value = get_config_value("analytics.collect_variable_usage", True)
    if isinstance(value, str):
        return value.lower() not in {"0", "false", "no"}
    return bool(value)


def _routing_metadata_from_request() -> tuple[
    str | None, ModalResolvedChannel | None
]:
    requested_version = request.environ.get(REQUESTED_VERSION_ENVIRON_KEY)
    resolved_channel = request.environ.get(RESOLVED_CHANNEL_ENVIRON_KEY)
    if not isinstance(requested_version, str) or not requested_version:
        return None, None

    try:
        channel = ModalResolvedChannel(resolved_channel)
    except ValueError:
        return None, None

    return requested_version, channel


def _set_observability_context_attributes(
    context: AnalyticsContext | None,
) -> None:
    if context is None:
        return
    set_attribute("country_id", context.country_id)
    set_attribute("api_version", context.api_version)
    set_attribute("model_version", context.model_version)
    set_attribute("requested_version", context.requested_version)
    if context.resolved_channel is not None:
        set_attribute("resolved_channel", context.resolved_channel)
    set_attribute(
        "distinct_variable_count",
        len({summary.variable_name for summary in context.variable_summaries}),
    )
