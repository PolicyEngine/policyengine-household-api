import pytest

from policyengine_household_api.modal_release.manifest import (
    apply_release_config,
    build_app_reference,
    cleanup_app_names_for_target,
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
