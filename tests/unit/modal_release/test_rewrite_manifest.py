import pytest

from policyengine_household_common.release_manifest import (
    MANIFEST_DICT_KEY,
)
from policyengine_household_api.modal_release.rewrite_manifest import (
    rewrite_modal_manifest,
)


def test_rewrite_modal_manifest_rejects_missing_manifest_without_writing():
    manifest_dict = {}

    with pytest.raises(ValueError, match="missing Modal release manifest"):
        rewrite_modal_manifest(manifest_dict)

    assert MANIFEST_DICT_KEY not in manifest_dict


def test_rewrite_modal_manifest_writes_rewritten_manifest():
    manifest_dict = {
        MANIFEST_DICT_KEY: {
            "schema_version": 1,
            "current": {
                "app_name": "current-app",
                "source_commit": "abc123",
                "package_versions": {
                    "uk": "2.31.0",
                    "us": "1.691.1",
                    "ca": "0.96.3",
                },
                "deployed_at": "2026-01-01T00:00:00+00:00",
            },
            "frontier": {
                "app_name": "frontier-app",
                "package_versions": {
                    "uk": "2.31.0",
                    "us": "1.692.0",
                    "ng": "0.5.1",
                },
                "deployed_at": "2026-01-02T00:00:00+00:00",
            },
            "retired": [
                {
                    "app_name": "old-app",
                    "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
                    "deployed_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
    }

    rewritten = rewrite_modal_manifest(manifest_dict)

    assert rewritten == {
        "schema_version": 1,
        "current": {
            "app_name": "current-app",
            "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
            "deployed_at": "2026-01-01T00:00:00+00:00",
        },
        "frontier": {
            "app_name": "frontier-app",
            "package_versions": {"uk": "2.31.0", "us": "1.692.0"},
            "deployed_at": "2026-01-02T00:00:00+00:00",
        },
        "retired": [],
    }
    assert rewritten["retired"] == []
    assert manifest_dict[MANIFEST_DICT_KEY] == rewritten


def test_rewrite_modal_manifest_rejects_missing_active_package_versions_without_writing():
    original_manifest = {
        "schema_version": 1,
        "current": {
            "app_name": "current-app",
            "package_versions": {"us": "1.691.1"},
            "deployed_at": "2026-01-01T00:00:00+00:00",
        },
        "frontier": None,
        "retired": [],
    }
    manifest_dict = {MANIFEST_DICT_KEY: original_manifest}

    with pytest.raises(ValueError, match="must declare"):
        rewrite_modal_manifest(manifest_dict)

    assert manifest_dict[MANIFEST_DICT_KEY] == original_manifest
