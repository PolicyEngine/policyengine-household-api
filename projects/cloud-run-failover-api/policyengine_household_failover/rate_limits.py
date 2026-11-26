"""Per-caller request rate limits for the public Cloud Run gateway.

The household app's own Flask-Limiter limits cannot tell callers apart once a
request reaches a Modal or Cloud Run worker: workers replay every request
through Flask's test client, so every caller appears as ``127.0.0.1``. The
gateway is the only process that sees both the validated Auth0 client ID and
the client's address, so it counts requests here, before dispatching them.

Counts are kept in each gateway process's memory, so a caller's effective
allowance is the configured limit multiplied by the number of gateway
processes that receive its requests.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import time

from flask import Flask, Request, Response, g, request
from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from policyengine_household_common.gateway import json_error_response


RATE_LIMIT_ENABLED_ENV = "HOUSEHOLD_FAILOVER_RATE_LIMIT_ENABLED"
TRUSTED_PROXY_COUNT_ENV = "HOUSEHOLD_FAILOVER_TRUSTED_PROXY_COUNT"
# Cloud Run's front end appends the connecting client's address as the last
# ``X-Forwarded-For`` entry. Each load balancer in front of Cloud Run appends
# one more entry, so deployments behind one should set this to 2.
DEFAULT_TRUSTED_PROXY_COUNT = 1

AUTH0_CLIENT_ID_CONTEXT_KEY = "auth0_client_id"
RATE_LIMIT_HEADER_NAMES = (
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
)


@dataclass(frozen=True)
class GatewayRateLimitConfig:
    enabled: bool = True
    trusted_proxy_count: int = DEFAULT_TRUSTED_PROXY_COUNT


@dataclass(frozen=True)
class RateLimitRule:
    """One rate-limited household API route and how its callers are counted.

    ``name`` scopes the counters, so all countries' requests to one route
    share a caller's allowance, matching the household app's own limits.
    """

    name: str
    limit: RateLimitItem
    count_by_auth0_client: bool


# Keep these in step with the ``@limiter.limit`` decorators in
# ``policyengine_household_api.api``, which still apply when the household
# app is deployed on its own.
CALCULATE_RULE = RateLimitRule(
    name="calculate",
    limit=parse("60 per minute"),
    count_by_auth0_client=True,
)
ANALYTICS_REQUESTS_RULE = RateLimitRule(
    name="analytics_calculate_requests",
    limit=parse("60 per minute"),
    count_by_auth0_client=True,
)
CALCULATE_DEMO_RULE = RateLimitRule(
    name="calculate_demo",
    limit=parse("1 per 10 seconds"),
    count_by_auth0_client=False,
)


def gateway_rate_limit_config_from_env() -> GatewayRateLimitConfig:
    return GatewayRateLimitConfig(
        enabled=_enabled_from_env(),
        trusted_proxy_count=_trusted_proxy_count_from_env(),
    )


def install_gateway_rate_limits(
    app: Flask,
    config: GatewayRateLimitConfig,
) -> None:
    """Reject over-limit requests before the gateway routes them.

    Register this after the hook that stores the validated Auth0 client ID
    in ``flask.g`` under ``AUTH0_CLIENT_ID_CONTEXT_KEY``.
    """

    if not config.enabled:
        return

    rate_limiter = FixedWindowRateLimiter(MemoryStorage())

    @app.before_request
    def _enforce_rate_limit() -> Response | None:
        rule = rate_limit_rule_for(request.method, request.path)
        if rule is None:
            return None

        caller_key = _caller_key(rule, request, config.trusted_proxy_count)
        allowed = rate_limiter.hit(rule.limit, rule.name, caller_key)
        window = rate_limiter.get_window_stats(
            rule.limit, rule.name, caller_key
        )
        g.rate_limit_headers = _rate_limit_headers(
            rule.limit,
            remaining=window.remaining,
            reset_time=window.reset_time,
        )
        if allowed:
            return None

        response = json_error_response(
            f"Rate limit exceeded: {rule.limit}",
            429,
            code="rate_limited",
        )
        response.headers["Retry-After"] = str(
            max(1, math.ceil(window.reset_time - time.time()))
        )
        _allow_cross_origin_read(response, request.headers.get("Origin"))
        return response

    @app.after_request
    def _add_rate_limit_headers(response: Response) -> Response:
        for name, value in g.get("rate_limit_headers", {}).items():
            response.headers[name] = value
        return response


def rate_limit_rule_for(method: str, path: str) -> RateLimitRule | None:
    """Return the rule for a request, mirroring the household app's routes."""

    path_segments = [segment for segment in path.split("/") if segment]
    if method == "POST" and len(path_segments) == 2:
        endpoint = path_segments[1]
        if endpoint == "calculate":
            return CALCULATE_RULE
        if endpoint == "calculate_demo":
            return CALCULATE_DEMO_RULE
    # Flask answers HEAD with the GET view, so HEAD shares GET's allowance.
    if method in ("GET", "HEAD") and path_segments == [
        "analytics",
        "calculate",
        "requests",
    ]:
        return ANALYTICS_REQUESTS_RULE
    return None


def client_ip_address(
    http_request: Request,
    trusted_proxy_count: int,
) -> str:
    """Return the caller's address as seen by the trusted proxies.

    Entries at the start of ``X-Forwarded-For`` come from the caller and can
    be forged, so read the entry that the outermost trusted proxy appended,
    counting from the end of the header. This follows the same rule as
    Werkzeug's ``ProxyFix(x_for=trusted_proxy_count)``.
    """

    connection_address = http_request.remote_addr or "unknown"
    if trusted_proxy_count == 0:
        return connection_address

    forwarded_entries = [
        entry.strip()
        for header_value in http_request.headers.getlist("X-Forwarded-For")
        for entry in header_value.split(",")
    ]
    if len(forwarded_entries) < trusted_proxy_count:
        return connection_address
    return forwarded_entries[-trusted_proxy_count] or connection_address


def _caller_key(
    rule: RateLimitRule,
    http_request: Request,
    trusted_proxy_count: int,
) -> str:
    if rule.count_by_auth0_client:
        client_id = g.get(AUTH0_CLIENT_ID_CONTEXT_KEY)
        if client_id:
            return f"auth0_client:{client_id}"
    return f"ip:{client_ip_address(http_request, trusted_proxy_count)}"


def _rate_limit_headers(
    limit: RateLimitItem,
    *,
    remaining: int,
    reset_time: float,
) -> dict[str, str]:
    limit_header, remaining_header, reset_header = RATE_LIMIT_HEADER_NAMES
    return {
        limit_header: str(limit.amount),
        remaining_header: str(max(0, remaining)),
        reset_header: str(math.ceil(reset_time)),
    }


def _allow_cross_origin_read(response: Response, origin: str | None) -> None:
    """Let browser pages on other origins read the gateway's 429 response.

    The household app answers with Flask-CORS's default policy, which
    allows every origin by echoing it. Responses the gateway forwards keep
    the app's headers; this 429 never reaches the app, so match that
    policy here and expose the headers a page needs to back off.
    """

    if not origin:
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.vary.add("Origin")
    response.headers["Access-Control-Expose-Headers"] = ", ".join(
        ("Retry-After", *RATE_LIMIT_HEADER_NAMES)
    )


def _enabled_from_env() -> bool:
    raw_value = os.getenv(RATE_LIMIT_ENABLED_ENV, "").strip()
    if not raw_value:
        return True
    normalized = raw_value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(
        f"{RATE_LIMIT_ENABLED_ENV} must be 'true' or 'false'; "
        f"received {raw_value!r}"
    )


def _trusted_proxy_count_from_env() -> int:
    raw_value = os.getenv(TRUSTED_PROXY_COUNT_ENV, "").strip()
    if not raw_value:
        return DEFAULT_TRUSTED_PROXY_COUNT
    try:
        trusted_proxy_count = int(raw_value)
    except ValueError:
        trusted_proxy_count = -1
    if trusted_proxy_count < 0:
        raise ValueError(
            f"{TRUSTED_PROXY_COUNT_ENV} must be a non-negative integer; "
            f"received {raw_value!r}"
        )
    return trusted_proxy_count
