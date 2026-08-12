"""Unit tests for auth/validation.py (JWKS lazy-fetch)."""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, Event
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

from policyengine_household_common import auth as validation
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
            "policyengine_household_common.auth.urlopen",
            side_effect=OSError("network down"),
        ):
            v = validation.Auth0JWTBearerTokenValidator(
                "bogus.auth0.com", "my-audience"
            )

        assert v.public_key is None

    def test__given_jwks_fetch_uses_timeout(self):
        """The JWKS fetch must pass a non-None timeout to urlopen."""
        with patch(
            "policyengine_household_common.auth.urlopen",
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

    def test__given_concurrent_retry__jwks_fetch_is_called_once(
        self,
        monkeypatch,
    ):
        """Concurrent callers must share one mocked JWKS retry."""
        issuer = "https://single-flight.auth0.com/"
        caller_count = 8
        callers_ready = Barrier(caller_count)
        fetch_started = Event()
        release_fetch = Event()
        validation._jwks_last_failure[issuer] = time.monotonic() - 60
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 30)

        def fake_fetch(_issuer):
            fetch_started.set()
            assert release_fetch.wait(timeout=2)
            return None

        def retry_fetch():
            callers_ready.wait(timeout=2)
            return validation._fetch_jwks(issuer)

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            side_effect=fake_fetch,
        ) as mock_fetch:
            with ThreadPoolExecutor(max_workers=caller_count) as executor:
                futures = [
                    executor.submit(retry_fetch) for _ in range(caller_count)
                ]
                assert fetch_started.wait(timeout=2)
                time.sleep(0.05)
                assert mock_fetch.call_count == 1
                release_fetch.set()
                results = [future.result(timeout=2) for future in futures]

        assert results == [None] * caller_count
        assert mock_fetch.call_count == 1

    def test__given_stale_cache__jwks_fetch_is_called_again(
        self,
        monkeypatch,
    ):
        """An expired successful cache entry must be refreshed."""
        monkeypatch.setattr(validation, "JWKS_CACHE_TTL_SECONDS", 0)
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 0)
        first_key_set = object()
        refreshed_key_set = object()

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            side_effect=(first_key_set, refreshed_key_set),
        ) as mock_fetch:
            first = validation._fetch_jwks("https://stale.auth0.com/")
            second = validation._fetch_jwks("https://stale.auth0.com/")

        assert first is first_key_set
        assert second is refreshed_key_set
        assert mock_fetch.call_count == 2

    def test__given_refresh_fails__last_known_good_jwks_is_retained(
        self,
        monkeypatch,
    ):
        """A transient refresh failure must not erase usable cached keys."""
        monkeypatch.setattr(validation, "JWKS_CACHE_TTL_SECONDS", 0)
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 0)
        cached_key_set = object()

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            side_effect=(cached_key_set, None),
        ) as mock_fetch:
            first = validation._fetch_jwks("https://retained.auth0.com/")
            after_failure = validation._fetch_jwks(
                "https://retained.auth0.com/"
            )

        assert first is cached_key_set
        assert after_failure is cached_key_set
        assert mock_fetch.call_count == 2

    def test__given_unknown_key_id__jwks_fetch_is_called_again(
        self,
        monkeypatch,
    ):
        """A token with a new key ID must trigger one bounded refresh."""
        monkeypatch.setattr(validation, "JWKS_RETRY_INTERVAL_SECONDS", 0)
        old_private_key = _private_key()
        new_private_key = _private_key()
        old_key_set = _key_set_for_key(old_private_key, "old-key")
        new_key_set = _key_set_for_key(new_private_key, "new-key")
        token = _signed_token(
            new_private_key,
            {
                "iss": "https://rotates.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
            },
            key_id="new-key",
        )

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            side_effect=(old_key_set, new_key_set),
        ) as mock_fetch:
            validator = validation.Auth0JWTBearerTokenValidator(
                "rotates.example",
                "audience",
            )
            claims = validator.authenticate_token(token)

        assert claims["sub"] == "client-id"
        assert mock_fetch.call_count == 2

    def test__given_repeated_unknown_key_id__jwks_refresh_is_throttled(self):
        """Unknown key IDs must not enable unbounded JWKS fetches."""
        trusted_private_key = _private_key()
        unknown_private_key = _private_key()
        trusted_key_set = _key_set_for_key(
            trusted_private_key,
            "trusted-key",
        )
        token = _signed_token(
            unknown_private_key,
            {
                "iss": "https://bounded.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
            },
            key_id="unknown-key",
        )
        issuer = "https://bounded.example/"

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            return_value=trusted_key_set,
        ) as mock_fetch:
            validator = validation.Auth0JWTBearerTokenValidator(
                "bounded.example",
                "audience",
            )
            validation._jwks_fetched_at[issuer] -= (
                validation.JWKS_RETRY_INTERVAL_SECONDS + 1
            )

            first = validator.authenticate_token(token)
            second = validator.authenticate_token(token)

        assert first is None
        assert second is None
        assert mock_fetch.call_count == 2

    def test__given_known_key_with_invalid_signature__jwks_is_not_refetched(
        self,
    ):
        """Invalid signatures must not let callers trigger JWKS traffic."""
        trusted_private_key = _private_key()
        untrusted_private_key = _private_key()
        trusted_key_set = _key_set_for_key(
            trusted_private_key,
            "known-key",
        )
        token = _signed_token(
            untrusted_private_key,
            {
                "iss": "https://stable.example/",
                "aud": "audience",
                "exp": int(time.time()) + 300,
                "sub": "client-id",
            },
            key_id="known-key",
        )

        with patch.object(
            validation,
            "_fetch_jwks_uncached",
            return_value=trusted_key_set,
        ) as mock_fetch:
            validator = validation.Auth0JWTBearerTokenValidator(
                "stable.example",
                "audience",
            )
            claims = validator.authenticate_token(token)

        assert claims is None
        assert mock_fetch.call_count == 1

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


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"client_id": "client-a"}, "client-a"),
        ({"azp": "client-a"}, "client-a"),
        (
            {"client_id": "client-a", "azp": "client-a"},
            "client-a",
        ),
        ({"sub": "client-a@clients"}, "client-a"),
        (
            {"client_id": "client-a", "sub": "client-a@clients"},
            "client-a",
        ),
        ({"azp": "client-a", "sub": "auth0|person-1"}, "client-a"),
    ],
)
def test_auth0_client_id_from_claims_accepts_supported_claims(
    claims,
    expected,
):
    assert validation.auth0_client_id_from_claims(claims) == expected


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sub": "auth0|person-1"},
        {"sub": "@clients"},
        {"client_id": "client-a", "azp": "client-b"},
        {"client_id": "client-a", "sub": "client-b@clients"},
        {"client_id": 123},
        {"client_id": "client-a", "azp": ["client-a"]},
        {"sub": ["client-a@clients"]},
    ],
)
def test_auth0_client_id_from_claims_rejects_ambiguous_or_human_claims(
    claims,
):
    assert validation.auth0_client_id_from_claims(claims) is None


def test_authenticated_auth0_client_id_validates_jwt_before_extraction():
    validation._clear_jwks_cache()
    private_key = _private_key()
    validator = _validator_for_key(private_key)
    token = _signed_token(
        private_key,
        {
            "iss": "https://tenant.example/",
            "aud": "audience",
            "exp": int(time.time()) + 300,
            "azp": "client-a",
            "sub": "client-a@clients",
        },
    )

    client_id = validation.authenticated_auth0_client_id(
        f"Bearer {token}",
        validator,
    )

    assert client_id == "client-a"


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Basic abc123",
        "Bearer",
        "Bearer ",
        "Bearer token extra",
    ],
)
def test_authenticated_auth0_client_id_ignores_missing_or_malformed_header(
    authorization,
):
    class UnexpectedValidator:
        def authenticate_token(self, _token):
            raise AssertionError("malformed headers must not reach validation")

    assert (
        validation.authenticated_auth0_client_id(
            authorization,
            UnexpectedValidator(),
        )
        is None
    )


def test_authenticated_auth0_client_id_ignores_invalid_token():
    class RejectingValidator:
        def authenticate_token(self, _token):
            return None

    assert (
        validation.authenticated_auth0_client_id(
            "Bearer invalid-token",
            RejectingValidator(),
        )
        is None
    )


def _private_key():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def _signed_token(
    private_key,
    claims: dict,
    *,
    key_id: str = "test-key",
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
        headers={"kid": key_id},
    )


def _key_set_for_key(private_key, key_id: str):
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update(
        {
            "kid": key_id,
            "use": "sig",
            "alg": "RS256",
        }
    )
    return validation.KeySet.import_key_set({"keys": [public_jwk]})


def _validator_for_key(private_key):
    key_set = _key_set_for_key(private_key, "test-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(key_set.as_dict()).encode()

    with patch(
        "policyengine_household_common.auth.urlopen",
        return_value=FakeResponse(),
    ):
        return validation.Auth0JWTBearerTokenValidator(
            "tenant.example",
            "audience",
        )
