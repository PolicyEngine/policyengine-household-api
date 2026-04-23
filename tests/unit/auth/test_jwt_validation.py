"""
Tests that authlib's JWTBearerTokenValidator.authenticate_token() works
with the same KeySet code path used in production.

These tests use self-signed RSA keys — no Auth0 credentials, no network
calls, no secrets. They exist to catch transitive dependency breakage
(e.g. authlib 1.7.0 delegating to joserfc which rejects authlib's KeySet).
"""

import time
import base64
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from authlib.jose.rfc7517.jwk import JsonWebKey
from authlib.jose import jwt as authlib_jwt
from authlib.oauth2.rfc7523 import JWTBearerTokenValidator


def _int_to_base64url(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def rsa_keypair():
    """Generate a fresh RSA key pair and JWKS for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "test-key-1",
                "alg": "RS256",
                "n": _int_to_base64url(public_numbers.n),
                "e": _int_to_base64url(public_numbers.e),
            }
        ]
    }
    return private_key, jwks


@pytest.fixture
def validator(rsa_keypair):
    """Create a JWTBearerTokenValidator with the test keyset."""
    _, jwks = rsa_keypair
    keyset = JsonWebKey.import_key_set(jwks)
    v = JWTBearerTokenValidator(keyset)
    v.claims_options = {
        "exp": {"essential": True},
        "aud": {"essential": True, "value": "test-audience"},
        "iss": {"essential": True, "value": "https://test.example.com/"},
    }
    return v


def _make_token(private_key, **claim_overrides) -> str:
    claims = {
        "iss": "https://test.example.com/",
        "aud": "test-audience",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "sub": "test-user@clients",
    }
    claims.update(claim_overrides)
    header = {"alg": "RS256", "kid": "test-key-1"}
    token = authlib_jwt.encode(header, claims, private_key)
    return token.decode() if isinstance(token, bytes) else token


class TestJWTBearerTokenValidation:
    """
    Exercises the exact code path used in production:
    JsonWebKey.import_key_set() -> JWTBearerTokenValidator -> authenticate_token()

    This is the path that broke when authlib 1.7.0 delegated to joserfc,
    which rejected authlib's KeySet type in guess_key().
    """

    def test_authenticate_token_with_valid_jwt(self, rsa_keypair, validator):
        """A correctly signed JWT must be accepted by authenticate_token()."""
        private_key, _ = rsa_keypair
        token = _make_token(private_key)
        result = validator.authenticate_token(token)
        assert result is not None
        assert result["sub"] == "test-user@clients"

    def test_authenticate_token_handles_expired_jwt(
        self, rsa_keypair, validator
    ):
        """An expired JWT must not crash the validator."""
        private_key, _ = rsa_keypair
        token = _make_token(private_key, exp=int(time.time()) - 60)
        # Must not raise — returning None (rejected) is acceptable
        result = validator.authenticate_token(token)

    def test_authenticate_token_rejects_wrong_key(self, validator):
        """A JWT signed with a different key must be rejected."""
        wrong_key = rsa.generate_private_key(
            65537, 2048, default_backend()
        )
        token = _make_token(wrong_key)
        result = validator.authenticate_token(token)
        assert result is None

    def test_import_key_set_returns_usable_keyset(self, rsa_keypair):
        """JsonWebKey.import_key_set must produce a keyset that
        JWTBearerTokenValidator can use without errors."""
        _, jwks = rsa_keypair
        keyset = JsonWebKey.import_key_set(jwks)
        # Must not raise
        JWTBearerTokenValidator(keyset)
