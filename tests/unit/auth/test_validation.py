"""Unit tests for auth/validation.py (JWKS lazy-fetch)."""

from unittest.mock import patch

from policyengine_household_api.auth import validation


class TestAuth0JWTBearerTokenValidator:
    def setup_method(self):
        # Clear the cache between tests so patches take effect.
        validation._fetch_jwks.cache_clear()

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
