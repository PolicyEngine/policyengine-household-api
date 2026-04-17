import json
import logging
from functools import lru_cache
from urllib.request import urlopen

from authlib.oauth2.rfc7523 import JWTBearerTokenValidator
from authlib.jose.rfc7517.jwk import JsonWebKey

logger = logging.getLogger(__name__)

JWKS_FETCH_TIMEOUT = 10  # seconds


@lru_cache(maxsize=8)
def _fetch_jwks(issuer: str):
    """
    Fetch the JWKS for an Auth0 issuer once per process.

    Returns an authlib key set, or ``None`` if the fetch fails. Errors
    are logged rather than raised so that a transient Auth0 outage
    doesn't crash the process at import time. Callers should handle
    the ``None`` return and either lazily retry or reject the token.
    """
    jwks_url = f"{issuer}.well-known/jwks.json"
    try:
        with urlopen(jwks_url, timeout=JWKS_FETCH_TIMEOUT) as response:
            return JsonWebKey.import_key_set(json.loads(response.read()))
    except Exception as e:
        logger.warning(f"Failed to fetch JWKS from {jwks_url}: {e}")
        return None


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
        # Lazy-refresh the JWKS if the initial fetch failed.
        if self.public_key is None:
            self.public_key = _fetch_jwks(self._issuer)
        return super().authenticate_token(token_string)
