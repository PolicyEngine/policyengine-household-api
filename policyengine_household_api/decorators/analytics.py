"""
Optional analytics decorator that only logs if analytics is enabled.
This decorator checks configuration before attempting to log analytics data.
"""

from functools import wraps
from flask import request
from datetime import datetime, timezone
import jwt
import logging
from uuid import uuid4
from policyengine_household_api.constants import VERSION
from policyengine_household_api.data.analytics_setup import (
    is_analytics_enabled,
    is_analytics_schema_ready,
)
from policyengine_household_api.data.analytics_setup import db
from policyengine_household_api.data.models import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)
from policyengine_household_api.models.analytics import (
    AnalyticsContext,
    ModalResolvedChannel,
    VariableUsageSummary,
)
from policyengine_household_api.observability import set_attribute
from policyengine_household_api.observability import segment
from policyengine_household_api.modal_release.routing_metadata import (
    REQUESTED_VERSION_ENVIRON_KEY,
    RESOLVED_CHANNEL_ENVIRON_KEY,
)
from policyengine_household_api.utils.variable_usage_analytics import (
    extract_variable_usage,
    stored_variable_name,
)
from policyengine_household_api.utils.config_loader import get_config_value

logger = logging.getLogger(__name__)


# Cache the JWKS client so we don't re-fetch keys on every request.
_jwks_client_cache: dict = {}


def _get_jwks_client(auth0_address: str):
    """Return a cached PyJWKClient for the given Auth0 domain."""
    if auth0_address not in _jwks_client_cache:
        jwks_url = f"https://{auth0_address}/.well-known/jwks.json"
        _jwks_client_cache[auth0_address] = jwt.PyJWKClient(jwks_url)
    return _jwks_client_cache[auth0_address]


def _verified_sub_claim(token: str) -> str | None:
    """
    Return the token's ``sub`` claim if signature verification succeeds
    against the configured Auth0 JWKS, else ``None``.

    If Auth0 configuration is missing (e.g. in a dev environment) the
    claim cannot be trusted and we return ``None`` so the caller can
    store a null client_id rather than an attacker-controlled value.
    """
    auth0_address = get_config_value("auth.auth0.address", "")
    auth0_audience = get_config_value("auth.auth0.audience", "")
    if not auth0_address or not auth0_audience:
        return None

    try:
        signing_key = _get_jwks_client(auth0_address).get_signing_key_from_jwt(
            token
        )
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=auth0_audience,
            issuer=f"https://{auth0_address}/",
            options={"verify_signature": True},
        )
    except Exception as e:
        logger.debug(f"JWT signature verification failed: {e}")
        return None

    return claims.get("sub")


def log_analytics_if_enabled(func):
    """
    Decorator that logs analytics only if analytics is enabled in configuration.

    If analytics is disabled, this passes through without logging. If
    analytics is enabled, analytics is required: schema readiness and
    database write failures propagate like other API failures.
    """

    @wraps(func)
    def decorated_function(*args, **kwargs):
        if not is_analytics_enabled():
            return func(*args, **kwargs)

        if not is_analytics_schema_ready():
            raise RuntimeError(
                "Analytics is enabled but the analytics database schema is "
                "not ready."
            )

        with segment("analytics_context_build"):
            analytics_context = _build_analytics_context(args, kwargs)
        _set_observability_context_attributes(analytics_context)

        try:
            response = func(*args, **kwargs)
        except Exception:
            with segment("analytics_write"):
                _record_analytics(analytics_context, 500)
            raise

        with segment("analytics_write"):
            _record_analytics(
                analytics_context,
                getattr(response, "status_code", None),
            )
        return response

    return decorated_function


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
    # Pull client_id from JWT. We only trust the `sub` claim when the token
    # signature has been verified against Auth0 JWKS. If verification fails,
    # store NULL so callers cannot spoof analytics identities.
    try:
        auth_header = str(request.authorization)
        token = auth_header.split(" ")[1]
        client_id = _verified_sub_claim(token)
        if client_id is None:
            return None

        suffix_to_slice = "@clients"
        if client_id.endswith(suffix_to_slice):
            return client_id[: -len(suffix_to_slice)]
        return client_id
    except Exception as e:
        logger.debug(f"Could not extract client_id from JWT: {e}")
        return None


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


def _record_analytics(
    context: AnalyticsContext | None,
    response_status_code: int | None,
) -> None:
    if context is None:
        return

    try:
        visit = _build_visit(context)
        db.session.add(visit)
        db.session.flush()
        visit_id = getattr(visit, "id", None)

        variable_summaries = context.variable_summaries
        calculate_request = _build_calculate_request(
            context,
            response_status_code,
            variable_summaries,
            visit_id,
        )

        if calculate_request is not None:
            db.session.add(calculate_request)
            db.session.flush()
            for summary in variable_summaries:
                db.session.add(
                    _build_calculate_request_variable(
                        calculate_request,
                        summary,
                    )
                )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to log analytics: {e}")
        raise


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


def _build_visit(context: AnalyticsContext) -> Visit:
    visit = Visit()
    visit.client_id = context.client_id
    visit.api_version = context.api_version
    visit.endpoint = context.endpoint
    visit.method = context.method.value
    visit.content_length_bytes = context.content_length_bytes
    visit.datetime = context.created_at
    return visit


def _build_calculate_request(
    context: AnalyticsContext,
    response_status_code: int | None,
    variable_summaries: tuple[VariableUsageSummary, ...],
    visit_id: int | None,
) -> CalculateRequest | None:
    if not context.record_calculate_request:
        return None
    if visit_id is None:
        raise ValueError("Visit ID is required for calculate analytics")

    distinct_variable_names = {
        summary.variable_name for summary in variable_summaries
    }
    unsupported_variable_names = {
        summary.variable_name
        for summary in variable_summaries
        if summary.availability_status == "unsupported"
    }
    deprecated_allowlisted_variable_names = {
        summary.variable_name
        for summary in variable_summaries
        if summary.availability_status == "deprecated_allowlisted"
    }

    calculate_request = CalculateRequest()
    calculate_request.visit_id = visit_id
    calculate_request.request_uuid = str(uuid4())
    calculate_request.client_id = context.client_id
    calculate_request.api_version = context.api_version
    calculate_request.country_id = context.country_id
    calculate_request.model_version = context.model_version
    calculate_request.requested_version = context.requested_version
    calculate_request.resolved_channel = (
        context.resolved_channel.value if context.resolved_channel else None
    )
    calculate_request.endpoint = context.endpoint
    calculate_request.method = context.method.value
    calculate_request.content_length_bytes = context.content_length_bytes
    calculate_request.response_status_code = response_status_code
    calculate_request.distinct_variable_count = len(distinct_variable_names)
    calculate_request.unsupported_variable_count = len(
        unsupported_variable_names
    )
    calculate_request.deprecated_allowlisted_variable_count = len(
        deprecated_allowlisted_variable_names
    )
    calculate_request.created_at = context.created_at
    return calculate_request


def _build_calculate_request_variable(
    calculate_request: CalculateRequest,
    summary: VariableUsageSummary,
) -> CalculateRequestVariable:
    variable = CalculateRequestVariable()
    variable.request_id = calculate_request.id
    variable.client_id = calculate_request.client_id
    variable.created_at = calculate_request.created_at
    variable.country_id = calculate_request.country_id
    variable.api_version = calculate_request.api_version
    variable.model_version = calculate_request.model_version
    variable.requested_version = calculate_request.requested_version
    variable.resolved_channel = calculate_request.resolved_channel
    variable.response_status_code = calculate_request.response_status_code
    (
        variable.variable_name,
        variable.variable_name_truncated,
    ) = stored_variable_name(summary.variable_name)
    variable.entity_type = summary.entity_type
    variable.source = summary.source.value
    variable.period_granularity = summary.period_granularity.value
    variable.entity_count = summary.entity_count
    variable.period_count = summary.period_count
    variable.occurrence_count = summary.occurrence_count
    variable.availability_status = summary.availability_status.value
    return variable
