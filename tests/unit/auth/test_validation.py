"""Unit tests for auth/validation.py (JWKS lazy-fetch)."""

import json
import time
from unittest.mock import patch

import pytest
import jwt
from authlib.oauth2.rfc6750.errors import (
    InsufficientScopeError,
    InvalidTokenError,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from policyengine_household_api.auth import validation
from policyengine_household_api.decorators.auth import ANALYTICS_READ_SCOPE


class TestAuth0JWTBearerTokenValidator:
    def setup_method(self):
        # Clear the cache between tests so patches take effect and one
        # test's failure timestamp doesn't throttle the next.
        validation._clear_jwks_cache()
        # Any historical retry-backoff must not leak into tests that
        # assume an immediate retry is allowed.
        validation._jwks_last_failure.clear()

    def test__given_jwks_fetch_fails__validator_constructs_with_none_key(self):
        """A failed JWKS fetch must not raise at import/construction time."""
        with patch(
            "policyengine_household_api.auth.validation.urlopen",
            side_effect=OSError("network down"),
        ):
            v = validation.Auth0JWTBearerTokenValidator(
                "bogus.auth0.com", "my-audience"
            )

        assert v.public_key is None

    def test__given_jwks_fetch_uses_timeout(self):
        """The JWKS fetch must pass a non-None timeout to urlopen."""
        with patch(
            "policyengine_household_api.auth.validation.urlopen",
            side_effect=OSError("network down"),
        ) as mock_urlopen:
            validation.Auth0JWTBearerTokenValidator(
                "bogus2.auth0.com", "my-audience"
            )

        assert mock_urlopen.call_count == 1
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") is not None
        assert kwargs["timeout"] > 0

    def test__given_jwks_fetch_fails_then_succeeds__lazy_retry_recovers(
        self, monkeypatch
    ):
        """The lazy retry must actually retry.

        Regression guard for the bug where ``_fetch_jwks`` was wrapped
        in ``@lru_cache`` — that memoised the ``None`` failure, so the
        "lazy retry" on the next authenticated request kept getting the
        cached ``None`` back and never hit the network again.

        Strategy: the first call to ``_fetch_jwks_uncached`` returns
        ``None``; the second returns a sentinel key. Construction must
        see ``None``; a later ``authenticate_token`` call must swap in
        the sentinel key, proving the network retry happened.
        """
        # Skip the retry-backoff so the second call reaches the fetch.
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 0)

        sentinel_key = object()
        calls = {"n": 0}

        def fake_fetch(_issuer):
            calls["n"] += 1
            return None if calls["n"] == 1 else sentinel_key

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            side_effect=fake_fetch,
        ):
            v = validation.Auth0JWTBearerTokenValidator(
                "recovers.auth0.com", "aud"
            )
            assert v.public_key is None

            # Stub out the parent authenticate_token so we only exercise
            # the retry plumbing, not authlib's JWT parsing.
            with patch.object(
                validation.JWTBearerTokenValidator,
                "authenticate_token",
                return_value="ok",
            ):
                v.authenticate_token("irrelevant-token")

        assert calls["n"] == 2, "lazy retry did not hit the network again"
        assert v.public_key is sentinel_key

    def test__given_recent_failure__retry_is_throttled(self, monkeypatch):
        """Back-to-back lazy retries after failure must not hammer Auth0."""
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 60)

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            return_value=None,
        ) as mock_fetch:
            validation._fetch_jwks("https://throttle.auth0.com/")
            validation._fetch_jwks("https://throttle.auth0.com/")
            validation._fetch_jwks("https://throttle.auth0.com/")

        # After the first failure, subsequent calls must short-circuit
        # on the failure timestamp and skip the network.
        assert mock_fetch.call_count == 1

    def test__given_successful_fetch__is_cached(self):
        """A successful JWKS must be cached so we don't re-fetch each request."""
        sentinel = object()
        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            return_value=sentinel,
        ) as mock_fetch:
            first = validation._fetch_jwks("https://cache.auth0.com/")
            second = validation._fetch_jwks("https://cache.auth0.com/")

        assert first is sentinel
        assert second is sentinel
        assert mock_fetch.call_count == 1

    def test__given_stale_cached_jwks__failed_token_validation_refreshes(
        self,
    ):
        """A stale successful JWKS cache must self-heal after key rotation."""
        old_private_key = _private_key()
        new_private_key = _private_key()
        responses = [
            _fake_jwks_response(old_private_key, kid="old-key"),
            _fake_jwks_response(new_private_key, kid="new-key"),
        ]

        with patch(
            "policyengine_household_api.auth.validation.urlopen",
            side_effect=responses,
        ) as mock_urlopen:
            validator = validation.Auth0JWTBearerTokenValidator(
                "tenant.example", "audience"
            )
            token = _signed_token(
                new_private_key,
                {
                    "iss": "https://tenant.example/",
                    "aud": "audience",
                    "exp": int(time.time()) + 300,
                    "sub": "client-id",
                },
                kid="new-key",
            )

            claims = validator.authenticate_token(token)

        assert claims["sub"] == "client-id"
        assert mock_urlopen.call_count == 2

    def test__given_repeated_invalid_tokens__forced_refresh_is_throttled(
        self, monkeypatch
    ):
        """Invalid tokens must not trigger a JWKS fetch on every request."""
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 60)
        private_key = _private_key()

        with patch(
            "policyengine_household_api.auth.validation.urlopen",
            return_value=_fake_jwks_response(private_key),
        ) as mock_urlopen:
            validator = validation.Auth0JWTBearerTokenValidator(
                "tenant.example", "audience"
            )
            token = _signed_token(
                _private_key(),
                {
                    "iss": "https://tenant.example/",
                    "aud": "audience",
                    "exp": int(time.time()) + 300,
                    "sub": "client-id",
                },
            )

            assert validator.authenticate_token(token) is None
            assert validator.authenticate_token(token) is None

        assert mock_urlopen.call_count == 2

    def test__given_rs256_jwks__authenticates_signed_token(self):
        """Regression guard for Authlib 1.7's joserfc key path."""
        private_key = _private_key()
        validator = _validator_for_key(private_key)
        token = _signed_token(
            private_key,
            {
                "iss": "https://tenant.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
            },
        )

        claims = validator.authenticate_token(token)

        assert claims["sub"] == "client-id"

    def test__given_valid_jwt_with_required_scope__validate_token_accepts(
        self,
    ):
        private_key = _private_key()
        validator = _validator_for_key(private_key)
        token = _signed_token(
            private_key,
            {
                "iss": "https://tenant.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
                "scope": ANALYTICS_READ_SCOPE,
            },
        )

        claims = validator.authenticate_token(token)
        validator.validate_token(claims, [ANALYTICS_READ_SCOPE], None)

    @pytest.mark.parametrize(
        "claim_overrides",
        [
            {"aud": "wrong-audience"},
            {"iss": "https://wrong-tenant.example/"},
            {"exp": int(time.time()) - 300},
        ],
    )
    def test__given_jwt_with_invalid_standard_claim__validate_token_rejects(
        self,
        claim_overrides,
    ):
        private_key = _private_key()
        validator = _validator_for_key(private_key)
        claims = {
            "iss": "https://tenant.example/",
            "aud": "audience",
            "exp": int(time.time()) + 300,
            "sub": "client-id",
            "scope": ANALYTICS_READ_SCOPE,
            **claim_overrides,
        }
        token = _signed_token(private_key, claims)

        parsed_claims = validator.authenticate_token(token)
        with pytest.raises(InvalidTokenError):
            validator.validate_token(
                parsed_claims, [ANALYTICS_READ_SCOPE], None
            )

    def test__given_jwt_signed_by_wrong_key__validate_token_rejects(self):
        trusted_key = _private_key()
        untrusted_key = _private_key()
        validator = _validator_for_key(trusted_key)
        token = _signed_token(
            untrusted_key,
            {
                "iss": "https://tenant.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
                "scope": ANALYTICS_READ_SCOPE,
            },
        )

        parsed_claims = validator.authenticate_token(token)
        with pytest.raises(InvalidTokenError):
            validator.validate_token(
                parsed_claims, [ANALYTICS_READ_SCOPE], None
            )

    def test__given_jwt_without_required_scope__validate_token_rejects(self):
        private_key = _private_key()
        validator = _validator_for_key(private_key)
        token = _signed_token(
            private_key,
            {
                "iss": "https://tenant.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
            },
        )

        claims = validator.authenticate_token(token)
        with pytest.raises(InsufficientScopeError):
            validator.validate_token(claims, [ANALYTICS_READ_SCOPE], None)

    def test__given_jwt_with_permissions_but_no_scope__validate_token_rejects(
        self,
    ):
        private_key = _private_key()
        validator = _validator_for_key(private_key)
        token = _signed_token(
            private_key,
            {
                "iss": "https://tenant.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
                "permissions": [ANALYTICS_READ_SCOPE],
            },
        )

        claims = validator.authenticate_token(token)
        with pytest.raises(InsufficientScopeError):
            validator.validate_token(claims, [ANALYTICS_READ_SCOPE], None)


def _private_key():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def _signed_token(
    private_key,
    claims: dict,
    *,
    kid: str = "test-key",
) -> str:
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return jwt.encode(
        claims,
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _fake_jwks_response(private_key, *, kid: str = "test-key"):
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update(
        {
            "kid": kid,
            "use": "sig",
            "alg": "RS256",
        }
    )
    jwks = {"keys": [public_jwk]}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(jwks).encode()

    return FakeResponse()


def _validator_for_key(private_key):
    with patch(
        "policyengine_household_api.auth.validation.urlopen",
        return_value=_fake_jwks_response(private_key),
    ):
        return validation.Auth0JWTBearerTokenValidator(
            "tenant.example",
            "audience",
        )
