import json
import logging
import time
from threading import Lock
from urllib.request import urlopen

from authlib.oauth2.rfc7523 import JWTBearerTokenValidator
from authlib.jose.rfc7517.jwk import JsonWebKey

logger = logging.getLogger(__name__)

JWKS_FETCH_TIMEOUT = 10  # seconds
# Minimum wait between back-to-back lazy retries after a failure.
# Keeps us from hammering Auth0 when it is actively degraded.
JWKS_RETRY_INTERVAL_SECONDS = 30


# Module-level cache of successful JWKS fetches, keyed by issuer. Only
# successes are cached so that a transient failure is retried on the
# next authenticated request (``lru_cache`` would have memoised the
# ``None`` return, making the "lazy retry" dead code).
_jwks_cache: dict = {}
# Records the monotonic timestamp of the most recent *failed* fetch
# per-issuer so we can rate-limit retries without caching the failure
# itself.
_jwks_last_failure: dict = {}
_jwks_lock = Lock()


def _fetch_jwks_uncached(issuer: str):
    """Fetch the JWKS for an Auth0 issuer, bypassing the cache.

    Returns an authlib key set on success, ``None`` on failure. Errors
    are logged rather than raised so that a transient Auth0 outage
    doesn't crash the process at import time.
    """
    jwks_url = f"{issuer}.well-known/jwks.json"
    try:
        with urlopen(jwks_url, timeout=JWKS_FETCH_TIMEOUT) as response:
            return JsonWebKey.import_key_set(json.loads(response.read()))
    except Exception as e:
        logger.warning(f"Failed to fetch JWKS from {jwks_url}: {e}")
        return None


def _fetch_jwks(issuer: str):
    """Fetch JWKS, caching only successful results.

    On failure we record the time but do not memoise the ``None`` — a
    later call will retry (subject to ``JWKS_RETRY_INTERVAL_SECONDS``
    backoff) so that the validator self-heals once Auth0 recovers.
    """
    with _jwks_lock:
        cached = _jwks_cache.get(issuer)
        if cached is not None:
            return cached
        last_failure = _jwks_last_failure.get(issuer)
        if (
            last_failure is not None
            and time.monotonic() - last_failure < JWKS_RETRY_INTERVAL_SECONDS
        ):
            # Too soon after the last failure — don't hammer Auth0.
            return None

    # Fetch outside the lock so a slow network call doesn't block
    # other threads that might be serving requests with a cached key.
    key_set = _fetch_jwks_uncached(issuer)

    with _jwks_lock:
        if key_set is not None:
            _jwks_cache[issuer] = key_set
            _jwks_last_failure.pop(issuer, None)
        else:
            _jwks_last_failure[issuer] = time.monotonic()
    return key_set


def _clear_jwks_cache():
    """Test helper: wipe the success/failure caches."""
    with _jwks_lock:
        _jwks_cache.clear()
        _jwks_last_failure.clear()


class Auth0JWTBearerTokenValidator(JWTBearerTokenValidator):
    def __init__(self, domain, audience):
        issuer = f"https://{domain}/"

        public_key = _fetch_jwks(issuer)
        if public_key is None:
            # Retry on next token validation rather than failing hard
            # at construction time. A missing key set means token
            # validation will fail cleanly inside authlib.
            logger.warning(
                "JWKS unavailable at construction; will retry on first "
                "token validation."
            )

        super(Auth0JWTBearerTokenValidator, self).__init__(public_key)
        self._issuer = issuer
        self.claims_options = {
            "exp": {"essential": True},
            "aud": {"essential": True, "value": audience},
            "iss": {"essential": True, "value": issuer},
        }

    def authenticate_token(self, token_string):
        # Lazy-refresh the JWKS if the initial fetch failed. Because
        # ``_fetch_jwks`` only caches successes, this call will retry
        # the network fetch (subject to a short backoff) until Auth0
        # responds.
        if self.public_key is None:
            self.public_key = _fetch_jwks(self._issuer)
        return super().authenticate_token(token_string)
