"""
Optional analytics decorator that only logs if analytics is enabled.
This decorator checks configuration before attempting to log analytics data.
"""

from functools import wraps
from flask import request
from datetime import datetime, timezone
import jwt
import logging
from policyengine_household_api.constants import VERSION
from policyengine_household_api.data.analytics_setup import (
    is_analytics_enabled,
)
from policyengine_household_api.data.analytics_setup import db
from policyengine_household_api.data.models import Visit
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

    This decorator:
    1. Checks if analytics is enabled
    2. If disabled, passes through without logging
    3. If enabled, logs the visit to the database
    """

    @wraps(func)
    def decorated_function(*args, **kwargs):
        # Check if analytics is enabled
        try:
            if not is_analytics_enabled():
                # Analytics disabled, just execute the function
                return func(*args, **kwargs)
        except Exception as e:
            logger.debug(f"Could not determine analytics status: {e}")
            # If we can't determine status, proceed without analytics
            return func(*args, **kwargs)

        # Analytics is enabled, proceed with logging
        try:
            # Create a record that will be emitted to the db
            new_visit = Visit()

            # Pull client_id from JWT. We only trust the `sub` claim
            # when the token signature has been verified against the
            # Auth0 JWKS. If verification fails (bad signature, JWKS
            # unreachable, etc.) we still record the visit but drop
            # the client_id so that attackers cannot spoof analytics
            # identities simply by crafting an unsigned JWT.
            try:
                auth_header = str(request.authorization)
                token = auth_header.split(" ")[1]
                client_id = _verified_sub_claim(token)

                if client_id is None:
                    new_visit.client_id = None
                else:
                    suffix_to_slice = "@clients"
                    if (
                        len(client_id) >= len(suffix_to_slice)
                        and client_id[-len(suffix_to_slice) :]
                        == suffix_to_slice
                    ):
                        client_id = client_id[: -len(suffix_to_slice)]
                    new_visit.client_id = client_id
            except Exception as e:
                logger.debug(f"Could not extract client_id from JWT: {e}")
                # Match the verified-fail path: a missing/unparseable
                # header must also be stored as NULL, never as a
                # sentinel string we'd have to filter out downstream.
                new_visit.client_id = None

            # Set API version
            new_visit.api_version = VERSION

            # Set endpoint and method
            new_visit.endpoint = request.endpoint
            new_visit.method = request.method

            # Set content_length_bytes
            new_visit.content_length_bytes = request.content_length

            # Set the date and time (timezone-aware; utcnow() is
            # deprecated in Python 3.12+)
            now = datetime.now(timezone.utc)
            new_visit.datetime = now

            # Emit the new record to the db
            db.session.add(new_visit)
            db.session.commit()

        except Exception as e:
            # Log the error but don't fail the request
            logger.error(f"Failed to log analytics: {e}")

        return func(*args, **kwargs)

    return decorated_function
