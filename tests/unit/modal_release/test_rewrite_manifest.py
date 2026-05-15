import pytest

from policyengine_household_api.modal_release.manifest import (
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
                "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
                "deployed_at": "2026-01-01T00:00:00+00:00",
            },
            "frontier": None,
            "retired": [
                {
                    "app_name": "current-app",
                    "package_versions": {"uk": "2.31.0", "us": "1.691.1"},
                    "deployed_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
    }

    rewritten = rewrite_modal_manifest(manifest_dict)

    assert rewritten["schema_version"] == 2
    assert rewritten["retired"] == []
    assert manifest_dict[MANIFEST_DICT_KEY] == rewritten
