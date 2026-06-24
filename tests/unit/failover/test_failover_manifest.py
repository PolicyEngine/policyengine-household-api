import pytest

from policyengine_household_api.failover.manifest import (
    FailoverManifestError,
    build_failover_manifest,
    public_versions_view,
    resolve_failover_channel_for_request,
    validate_failover_manifest,
)
from policyengine_household_api.version_routing import VersionRoutingError


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
    assert manifest["retired"] == []


def test_build_failover_manifest_carries_retired_versions():
    modal_manifest = _modal_manifest()
    modal_manifest["retired"] = [
        {
            "app_name": "modal-retired",
            "package_versions": {"uk": "2.20.0", "us": "0.9.0"},
            "deployed_at": "2025-12-25T00:00:00+00:00",
            "retired_at": "2026-01-01T00:00:00+00:00",
            "retirement_reason": "replaced-current",
        }
    ]

    manifest = build_failover_manifest(
        environment="staging",
        modal_manifest=modal_manifest,
        worker_urls={
            "current": "https://current.run.app",
            "frontier": "https://frontier.run.app",
        },
        generated_at="2026-06-03T00:00:00+00:00",
    )

    assert manifest["retired"] == [
        {
            "modal_app_name": "modal-retired",
            "package_versions": {"uk": "2.20.0", "us": "0.9.0"},
            "deployed_at": "2025-12-25T00:00:00+00:00",
            "retired_at": "2026-01-01T00:00:00+00:00",
            "retirement_reason": "replaced-current",
        }
    ]


def test_validates_failover_manifest_without_retired_field():
    manifest = _manifest()
    del manifest["retired"]

    assert validate_failover_manifest(manifest)["retired"] == []


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
    with pytest.raises(VersionRoutingError, match="9.9.9") as exc_info:
        resolve_failover_channel_for_request(
            _manifest(),
            country_id="us",
            requested_version="9.9.9",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "unsupported_version"
    assert exc_info.value.requested_version == "9.9.9"
    assert exc_info.value.country_id == "us"
    assert exc_info.value.available_versions == {
        "current": "1.0.0",
        "frontier": "2.0.0",
    }


def test_rejects_retired_exact_package_version():
    manifest = _manifest()
    manifest["retired"] = [
        {
            "modal_app_name": "modal-retired",
            "package_versions": {"uk": "2.20.0", "us": "0.9.0"},
        }
    ]

    with pytest.raises(VersionRoutingError, match="0.9.0") as exc_info:
        resolve_failover_channel_for_request(
            manifest,
            country_id="us",
            requested_version="0.9.0",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "deprecated_version"
    assert exc_info.value.requested_version == "0.9.0"
    assert exc_info.value.country_id == "us"
    assert exc_info.value.available_versions == {
        "current": "1.0.0",
        "frontier": "2.0.0",
    }


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
