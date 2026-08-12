from __future__ import annotations

from base64 import urlsafe_b64decode
from binascii import Error as Base64DecodeError
from collections.abc import Mapping
import json
import logging
import time
from threading import Event, Lock
from typing import Any
from urllib.request import urlopen

from authlib.oauth2.rfc7523 import JWTBearerTokenValidator
from authlib.oauth2.rfc6749.errors import OAuth2Error
from joserfc.jwk import KeySet


logger = logging.getLogger(__name__)

JWKS_FETCH_TIMEOUT = 10
JWKS_RETRY_INTERVAL_SECONDS = 30
JWKS_CACHE_TTL_SECONDS = 300

_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: dict[str, float] = {}
_jwks_last_failure: dict[str, float] = {}
_jwks_refresh_in_progress: dict[str, Event] = {}
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


def _fetch_jwks(
    issuer: str,
    *,
    force_refresh: bool = False,
) -> Any | None:
    """Return an issuer's JWKS with bounded, single-flight refreshes."""
    wait_for_refresh = None
    started_refresh = None
    cached = None
    now = time.monotonic()
    with _jwks_lock:
        cached = _jwks_cache.get(issuer)
        fetched_at = _jwks_fetched_at.get(issuer)
        cache_is_fresh = (
            fetched_at is not None
            and now - fetched_at < JWKS_CACHE_TTL_SECONDS
        )
        if cached is not None and cache_is_fresh and not force_refresh:
            return cached

        last_failure = _jwks_last_failure.get(issuer)
        last_attempt = (
            max(
                timestamp
                for timestamp in (fetched_at, last_failure)
                if timestamp is not None
            )
            if fetched_at is not None or last_failure is not None
            else None
        )
        if last_attempt is not None and (
            now - last_attempt < JWKS_RETRY_INTERVAL_SECONDS
        ):
            return cached

        refresh_in_progress = _jwks_refresh_in_progress.get(issuer)
        if refresh_in_progress is not None:
            if cached is not None and not force_refresh:
                return cached
            wait_for_refresh = refresh_in_progress
        else:
            started_refresh = Event()
            _jwks_refresh_in_progress[issuer] = started_refresh

    if wait_for_refresh is not None:
        wait_for_refresh.wait(timeout=JWKS_FETCH_TIMEOUT + 1)
        with _jwks_lock:
            return _jwks_cache.get(issuer, cached)

    try:
        key_set = _fetch_jwks_uncached(issuer)
    except Exception:
        logger.exception("Unexpected error fetching JWKS for %s", issuer)
        key_set = None

    with _jwks_lock:
        if key_set is not None:
            _jwks_cache[issuer] = key_set
            _jwks_fetched_at[issuer] = time.monotonic()
            _jwks_last_failure.pop(issuer, None)
        else:
            _jwks_last_failure[issuer] = time.monotonic()
        if _jwks_refresh_in_progress.get(issuer) is started_refresh:
            _jwks_refresh_in_progress.pop(issuer)
        if started_refresh is not None:
            started_refresh.set()
        return _jwks_cache.get(issuer, cached)


def _clear_jwks_cache() -> None:
    """Clear successful and failed JWKS fetch state for tests."""
    with _jwks_lock:
        _jwks_cache.clear()
        _jwks_fetched_at.clear()
        _jwks_last_failure.clear()
        for refresh_complete in _jwks_refresh_in_progress.values():
            refresh_complete.set()
        _jwks_refresh_in_progress.clear()


def _token_key_id(token_string: str) -> str | None:
    """Read an untrusted JWT key ID for key selection only."""
    try:
        encoded_header, _, _ = token_string.split(".")
        padding = "=" * (-len(encoded_header) % 4)
        header = json.loads(
            urlsafe_b64decode(encoded_header + padding).decode()
        )
    except (
        Base64DecodeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None
    if not isinstance(header, Mapping):
        return None
    key_id = header.get("kid")
    return key_id if isinstance(key_id, str) and key_id else None


def _key_set_contains_key_id(key_set: Any, key_id: str) -> bool:
    """Return whether a JWKS-like key set contains the requested key ID."""
    if not isinstance(key_set, KeySet):
        return True
    return any(key.kid == key_id for key in key_set)


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
        key_set = _fetch_jwks(self._issuer)
        if key_set is not None:
            self.public_key = key_set

        key_id = _token_key_id(token_string)
        if (
            key_id is not None
            and self.public_key is not None
            and not _key_set_contains_key_id(self.public_key, key_id)
        ):
            refreshed_key_set = _fetch_jwks(
                self._issuer,
                force_refresh=True,
            )
            if refreshed_key_set is not None:
                self.public_key = refreshed_key_set
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
