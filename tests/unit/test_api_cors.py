"""Unit tests for the default CORS origin allowlist in `api._resolve_cors_origins`.

Flask-CORS matches origins with ``re.match``, which is a prefix match.
That means an unanchored regex like ``https://.*\\.policyengine\\.org``
will happily match ``https://evil.policyengine.org.attacker.com``. The
defaults must therefore be anchored with ``$``.
"""

import os
import re
from unittest import mock

import pytest


@pytest.fixture
def resolve_cors_origins(monkeypatch):
    """Import the helper with a clean env so the default branch is used."""
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    # The config loader may pull in a value; neutralise it.
    with mock.patch(
        "policyengine_household_api.api.get_config_value",
        return_value=None,
    ):
        from policyengine_household_api.api import _resolve_cors_origins

        yield _resolve_cors_origins


_REGEX_HINT_CHARS = {"*", "\\", "]", "?", "$", "^", "[", "(", ")"}


def _looks_like_regex(pattern):
    """Mirror ``flask_cors.core.probably_regex`` so tests compare the
    same way flask-cors will at request time."""
    return any(c in pattern for c in _REGEX_HINT_CHARS)


def _matches(origins, candidate):
    """Replicate flask_cors's matching semantics: entries that look
    like regex are applied with ``re.match`` (prefix match), everything
    else is compared for case-insensitive equality.
    """
    for origin in origins:
        if _looks_like_regex(origin):
            try:
                if re.match(origin, candidate, flags=re.IGNORECASE):
                    return True
            except re.error:
                continue
        else:
            if candidate.casefold() == origin.casefold():
                return True
    return False


class TestDefaultCorsOrigins:
    def test__given_attacker_host_with_policyengine_prefix__is_rejected(
        self, resolve_cors_origins
    ):
        """Without a trailing ``$`` anchor, the wildcard regex matches
        a hostile host whose suffix is ``.attacker.com``. This test is
        the regression guard for that bypass.
        """
        origins = resolve_cors_origins()
        assert not _matches(origins, "https://policyengine.org.attacker.com")
        assert not _matches(
            origins, "https://evil.policyengine.org.attacker.com"
        )

    def test__given_legitimate_subdomains__are_accepted(
        self, resolve_cors_origins
    ):
        origins = resolve_cors_origins()
        assert _matches(origins, "https://policyengine.org")
        assert _matches(origins, "https://api.policyengine.org")
        assert _matches(origins, "https://app.policyengine.org")

    def test__given_localhost_dev_origin__is_accepted(
        self, resolve_cors_origins
    ):
        """Local dev servers (any port on localhost / 127.0.0.1) must
        reach the API without the operator setting
        ``CORS_ALLOWED_ORIGINS`` by hand."""
        origins = resolve_cors_origins()
        assert _matches(origins, "http://localhost:3000")
        assert _matches(origins, "http://localhost")
        assert _matches(origins, "http://127.0.0.1:5173")

    def test__given_localhost_lookalike__is_rejected(
        self, resolve_cors_origins
    ):
        origins = resolve_cors_origins()
        assert not _matches(origins, "http://localhost.attacker.com")
        assert not _matches(origins, "http://127.0.0.1.attacker.com")

    def test__given_env_override__wins_over_defaults(self, monkeypatch):
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            "https://foo.example.com, https://bar.example.com",
        )
        from policyengine_household_api.api import _resolve_cors_origins

        origins = _resolve_cors_origins()
        assert origins == [
            "https://foo.example.com",
            "https://bar.example.com",
        ]
