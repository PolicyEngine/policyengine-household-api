import pytest

from policyengine_household_api.failover.manifest import (
    FailoverManifestError,
    build_failover_manifest,
    public_versions_view,
    resolve_failover_channel_for_request,
    validate_failover_manifest,
)


def _modal_manifest():
    return {
        "schema_version": 1,
        "current": {
            "app_name": "modal-current",
            "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
            "deployed_at": "2026-01-01T00:00:00+00:00",
            "analytics_database_revision": "20260519_0004",
        },
        "frontier": {
            "app_name": "modal-frontier",
            "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
            "deployed_at": "2026-01-02T00:00:00+00:00",
        },
        "retired": [],
    }


def _manifest():
    return build_failover_manifest(
        environment="staging",
        modal_manifest=_modal_manifest(),
        worker_urls={
            "current": "https://current.run.app",
            "frontier": "https://frontier.run.app",
        },
        generated_at="2026-06-03T00:00:00+00:00",
    )


def test_build_failover_manifest_from_modal_manifest():
    manifest = _manifest()

    assert manifest["channels"]["current"] == {
        "modal_app_name": "modal-current",
        "cloud_run_worker_url": "https://current.run.app",
        "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
        "deployed_at": "2026-01-01T00:00:00+00:00",
        "analytics_database_revision": "20260519_0004",
    }


def test_resolves_current_channel():
    resolved = resolve_failover_channel_for_request(
        _manifest(),
        country_id="us",
        requested_version="current",
    )

    assert resolved.channel == "current"
    assert resolved.modal_app_name == "modal-current"
    assert resolved.cloud_run_worker_url == "https://current.run.app"


def test_resolves_exact_package_version():
    resolved = resolve_failover_channel_for_request(
        _manifest(),
        country_id="us",
        requested_version="2.0.0",
    )

    assert resolved.channel == "frontier"
    assert resolved.requested_version == "2.0.0"


def test_rejects_unknown_exact_package_version():
    with pytest.raises(FailoverManifestError, match="9.9.9"):
        resolve_failover_channel_for_request(
            _manifest(),
            country_id="us",
            requested_version="9.9.9",
        )


def test_rejects_unsupported_manifest_schema_version():
    manifest = {**_manifest(), "schema_version": 999}

    with pytest.raises(FailoverManifestError, match="schema version"):
        validate_failover_manifest(manifest)


def test_public_versions_view_omits_worker_urls():
    view = public_versions_view(_manifest())

    assert view == {
        "schema_version": 1,
        "current": {
            "app_name": "modal-current",
            "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
            "deployed_at": "2026-01-01T00:00:00+00:00",
            "analytics_database_revision": "20260519_0004",
        },
        "frontier": {
            "app_name": "modal-frontier",
            "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
            "deployed_at": "2026-01-02T00:00:00+00:00",
        },
    }
