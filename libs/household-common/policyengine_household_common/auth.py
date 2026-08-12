from __future__ import annotations

from collections.abc import Mapping
import json
import logging
import time
from threading import Lock
from typing import Any
from urllib.request import urlopen

from authlib.oauth2.rfc7523 import JWTBearerTokenValidator
from authlib.oauth2.rfc6749.errors import OAuth2Error
from joserfc.jwk import KeySet


logger = logging.getLogger(__name__)

JWKS_FETCH_TIMEOUT = 10
JWKS_RETRY_INTERVAL_SECONDS = 30

_jwks_cache: dict[str, Any] = {}
_jwks_last_failure: dict[str, float] = {}
_jwks_lock = Lock()


def _fetch_jwks_uncached(issuer: str) -> Any | None:
    """Fetch an issuer's JWKS without caching failures."""
    jwks_url = f"{issuer}.well-known/jwks.json"
    try:
        with urlopen(jwks_url, timeout=JWKS_FETCH_TIMEOUT) as response:
            return KeySet.import_key_set(json.loads(response.read()))
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", jwks_url, exc)
        return None


def _fetch_jwks(issuer: str) -> Any | None:
    """Fetch JWKS, caching successes and rate-limiting failed retries."""
    with _jwks_lock:
        cached = _jwks_cache.get(issuer)
        if cached is not None:
            return cached
        last_failure = _jwks_last_failure.get(issuer)
        if (
            last_failure is not None
            and time.monotonic() - last_failure < JWKS_RETRY_INTERVAL_SECONDS
        ):
            return None

    key_set = _fetch_jwks_uncached(issuer)

    with _jwks_lock:
        if key_set is not None:
            _jwks_cache[issuer] = key_set
            _jwks_last_failure.pop(issuer, None)
        else:
            _jwks_last_failure[issuer] = time.monotonic()
    return key_set


def _clear_jwks_cache() -> None:
    """Clear successful and failed JWKS fetch state for tests."""
    with _jwks_lock:
        _jwks_cache.clear()
        _jwks_last_failure.clear()


class Auth0JWTBearerTokenValidator(JWTBearerTokenValidator):
    def __init__(self, domain: str, audience: str):
        issuer = f"https://{domain}/"
        public_key = _fetch_jwks(issuer)
        if public_key is None:
            logger.warning(
                "JWKS unavailable at construction; will retry on first "
                "token validation."
            )

        super().__init__(public_key)
        self._issuer = issuer
        self.claims_options = {
            "exp": {"essential": True},
            "aud": {"essential": True, "value": audience},
            "iss": {"essential": True, "value": issuer},
        }

    def authenticate_token(self, token_string: str) -> Any | None:
        if self.public_key is None:
            self.public_key = _fetch_jwks(self._issuer)
        return super().authenticate_token(token_string)


def authenticated_auth0_client_id(
    authorization: str | None,
    validator: Auth0JWTBearerTokenValidator,
) -> str | None:
    """Return the caller client ID only after validating its bearer JWT."""
    if not isinstance(authorization, str):
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None

    token = validator.authenticate_token(parts[1])
    if token is None:
        return None
    try:
        validator.validate_token(token, [], None)
    except OAuth2Error:
        return None
    return auth0_client_id_from_claims(token)


def auth0_client_id_from_claims(claims: Mapping[str, Any]) -> str | None:
    """Normalize Auth0's supported application-client claim profiles.

    Auth0's RFC 9068 profile uses ``client_id`` while its default token
    profile uses ``azp``. Machine-to-machine tokens may additionally identify
    the client through ``<client_id>@clients`` in ``sub``. A human subject is
    never treated as a client identifier.
    """
    for claim_name in ("client_id", "azp", "sub"):
        if claim_name in claims:
            value = claims[claim_name]
            if not isinstance(value, str) or not value:
                return None

    client_id = claims.get("client_id")
    authorized_party = claims.get("azp")
    subject = claims.get("sub")

    if (
        client_id is not None
        and authorized_party is not None
        and client_id != authorized_party
    ):
        return None

    normalized = client_id or authorized_party
    machine_client_id = None
    if subject is not None and subject.endswith("@clients"):
        machine_client_id = subject[: -len("@clients")]
        if not machine_client_id:
            return None

    if (
        normalized is not None
        and machine_client_id is not None
        and normalized != machine_client_id
    ):
        return None
    return normalized or machine_client_id
