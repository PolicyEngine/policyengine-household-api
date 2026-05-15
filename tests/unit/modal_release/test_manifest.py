import pytest

from policyengine_household_api.modal_release.manifest import (
    MANIFEST_SCHEMA_VERSION,
    active_app_deployments,
    apply_release_config,
    build_app_reference,
    build_app_name,
    cleanup_app_names_for_target,
    current_package_versions,
    normalize_manifest,
    rewrite_manifest_for_storage,
)
from policyengine_household_api.modal_release import (
    manifest as manifest_module,
)
from policyengine_household_api.modal_release.release_config import (
    CleanupTarget,
    ModalReleaseConfig,
    NewAppTarget,
)


def _app(name):
    return {
        "app_name": name,
        "package_versions": {"us": "1.0.0"},
        "deployed_at": "2026-01-01T00:00:00+00:00",
    }


def test_default_release_promotes_frontier_and_retires_current():
    manifest = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": _app("frontier-app"),
        "retired": [],
    }
    config = ModalReleaseConfig(
        new_app_target=NewAppTarget.FRONTIER,
        promote_existing_frontier=True,
        cleanup_target=CleanupTarget.NONE,
    )

    updated = apply_release_config(
        manifest,
        config,
        new_app=_app("new-frontier-app"),
        timestamp="2026-01-02T00:00:00+00:00",
    )

    assert updated["current"]["app_name"] == "frontier-app"
    assert updated["frontier"]["app_name"] == "new-frontier-app"
    assert updated["retired"][0]["app_name"] == "current-app"
    assert updated["retired"][0]["retirement_reason"] == "replaced-current"


def test_direct_current_release_retires_current_and_frontier():
    manifest = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": _app("frontier-app"),
        "retired": [],
    }
    config = ModalReleaseConfig(
        new_app_target=NewAppTarget.CURRENT,
        promote_existing_frontier=False,
        cleanup_target=CleanupTarget.NONE,
    )

    updated = apply_release_config(
        manifest,
        config,
        new_app=_app("new-current-app"),
        timestamp="2026-01-02T00:00:00+00:00",
    )

    assert updated["current"]["app_name"] == "new-current-app"
    assert updated["frontier"] is None
    assert [app["app_name"] for app in updated["retired"]] == [
        "current-app",
        "frontier-app",
    ]


def test_retired_cleanup_excludes_active_apps():
    manifest = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": _app("frontier-app"),
        "retired": [_app("current-app"), _app("old-app")],
    }

    assert cleanup_app_names_for_target(
        manifest,
        CleanupTarget.RETIRED,
    ) == ["old-app"]


def test_active_cleanup_is_refused():
    manifest = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": None,
        "retired": [],
    }

    with pytest.raises(ValueError, match="Refusing"):
        cleanup_app_names_for_target(manifest, CleanupTarget.CURRENT)


def test_replaced_active_cleanup_uses_previous_channel_app():
    previous = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": _app("frontier-app"),
        "retired": [],
    }
    updated = {
        "schema_version": 1,
        "current": _app("new-current-app"),
        "frontier": None,
        "retired": [_app("current-app"), _app("frontier-app")],
    }

    assert cleanup_app_names_for_target(
        updated,
        CleanupTarget.FRONTIER,
        previous_manifest=previous,
    ) == ["frontier-app"]


def test_previous_active_cleanup_refuses_still_active_app():
    previous = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": _app("frontier-app"),
        "retired": [],
    }
    updated = {
        "schema_version": 1,
        "current": _app("frontier-app"),
        "frontier": _app("new-frontier-app"),
        "retired": [_app("current-app")],
    }

    with pytest.raises(ValueError, match="Refusing"):
        cleanup_app_names_for_target(
            updated,
            CleanupTarget.FRONTIER,
            previous_manifest=previous,
        )


def test_app_reference_includes_analytics_migration_metadata():
    app = build_app_reference(
        app_name="worker-app",
        package_versions={"us": "1.0.0"},
        deployed_at="2026-01-01T00:00:00+00:00",
        analytics_database_revision="20260512_0003",
    )

    assert app["analytics_migration_minimum_revision"] == "20260512_0003"
    assert app["analytics_database_revision"] == "20260512_0003"
    assert "source_commit" not in app


def test_app_reference_only_records_release_package_versions():
    app = build_app_reference(
        app_name="worker-app",
        package_versions={
            "uk": "2.31.0",
            "us": "1.691.1",
            "ca": "0.96.3",
            "ng": "0.5.1",
            "il": "0.1.0",
        },
        deployed_at="2026-01-01T00:00:00+00:00",
    )

    assert app["package_versions"] == {"uk": "2.31.0", "us": "1.691.1"}


def test_app_name_only_includes_us_and_uk_package_versions():
    app_name = build_app_name(
        {
            "uk": "2.31.0",
            "us": "1.691.1",
            "ca": "0.96.3",
            "ng": "0.5.1",
            "il": "0.1.0",
        }
    )

    assert app_name == "policyengine-household-api-uk2-31-0-us1-691-1"


def test_current_package_versions_only_includes_us_and_uk(monkeypatch):
    monkeypatch.setattr(
        manifest_module,
        "COUNTRY_PACKAGE_VERSIONS",
        {
            "uk": "2.31.0",
            "us": "1.691.1",
            "ca": "0.96.3",
            "ng": "0.5.1",
            "il": "0.1.0",
        },
    )

    assert current_package_versions() == {"uk": "2.31.0", "us": "1.691.1"}


def test_normalize_manifest_upgrades_legacy_manifest_and_removes_source_commit():
    manifest = {
        "schema_version": 1,
        "current": {
            **_app("current-app"),
            "source_commit": "abc123",
            "package_versions": {
                "uk": "2.31.0",
                "us": "1.691.1",
                "ca": "0.96.3",
            },
        },
        "frontier": None,
        "retired": [
            {
                **_app("old-app"),
                "source_commit": "def456",
                "package_versions": {
                    "uk": "2.31.0",
                    "us": "1.690.0",
                    "ng": "0.5.1",
                },
            }
        ],
    }

    normalized = normalize_manifest(manifest)

    assert normalized["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert "source_commit" not in normalized["current"]
    assert normalized["current"]["package_versions"] == {
        "uk": "2.31.0",
        "us": "1.691.1",
    }
    assert "source_commit" not in normalized["retired"][0]
    assert normalized["retired"][0]["package_versions"] == {
        "uk": "2.31.0",
        "us": "1.690.0",
    }


def test_active_app_deployments_deduplicates_matching_active_app_names():
    manifest = {
        "schema_version": 2,
        "current": {
            **_app("shared-app"),
            "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
        },
        "frontier": {
            **_app("shared-app"),
            "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
        },
        "retired": [],
    }

    assert active_app_deployments(manifest) == [
        {
            "app_name": "shared-app",
            "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
        }
    ]


def test_active_app_deployments_rejects_conflicting_active_app_versions():
    manifest = {
        "schema_version": 2,
        "current": {
            **_app("shared-app"),
            "package_versions": {"uk": "2.31.0", "us": "1.690.0"},
        },
        "frontier": {
            **_app("shared-app"),
            "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
        },
        "retired": [],
    }

    with pytest.raises(ValueError, match="conflicting package versions"):
        active_app_deployments(manifest)


def test_rewrite_manifest_removes_active_and_duplicate_retired_apps():
    manifest = {
        "schema_version": 1,
        "current": _app("current-app"),
        "frontier": _app("frontier-app"),
        "retired": [
            _app("current-app"),
            _app("old-app"),
            _app("old-app"),
            _app("older-app"),
        ],
    }

    rewritten = rewrite_manifest_for_storage(manifest)

    assert rewritten["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert [app["app_name"] for app in rewritten["retired"]] == [
        "old-app",
        "older-app",
    ]
