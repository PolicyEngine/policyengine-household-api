"""Unit tests for auth/validation.py (JWKS lazy-fetch)."""

from unittest.mock import patch

import pytest

from policyengine_household_api.auth import validation


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
