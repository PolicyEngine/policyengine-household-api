import json
import sys

import modal

from policyengine_household_api.modal_release import update_manifest
from policyengine_household_api.modal_release.manifest import MANIFEST_DICT_KEY


def _app(name, *, uk="2.31.0", us="1.691.1"):
    return {
        "app_name": name,
        "package_versions": {"uk": uk, "us": us},
        "deployed_at": "2026-01-01T00:00:00+00:00",
    }


class _FakeModalDict:
    def __init__(self, initial):
        self._store = dict(initial)

    def get(self, key, default=None):
        return self._store.get(key, default)

    def __getitem__(self, key):
        return self._store[key]

    def __setitem__(self, key, value):
        self._store[key] = value


def _fake_dict_type(instance):
    class _FakeDictType:
        @classmethod
        def from_name(cls, *args, **kwargs):
            return instance

    return _FakeDictType


def test_update_manifest_prunes_cleaned_retired_apps(tmp_path, monkeypatch):
    initial_manifest = {
        "schema_version": 1,
        "current": _app("current-app", us="1.726.0"),
        "frontier": _app("frontier-app", us="1.732.0"),
        # A long-since-deleted app that keeps getting re-listed for cleanup.
        "retired": [_app("ghost-app", us="1.691.1")],
    }
    fake_dict = _FakeModalDict({MANIFEST_DICT_KEY: initial_manifest})
    monkeypatch.setattr(
        update_manifest.modal, "Dict", _fake_dict_type(fake_dict)
    )

    config = json.dumps(
        {
            "new_app_target": "frontier",
            "promote_existing_frontier": True,
            "cleanup_target": "retired",
        }
    )
    cleanup_output = tmp_path / "modal-cleanup.json"
    manifest_output = tmp_path / "modal-manifest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_manifest.py",
            "--config-json",
            config,
            "--new-app-name",
            "new-frontier-app",
            "--analytics-database-revision",
            "rev-123",
            "--modal-environment",
            "testing",
            "--cleanup-output",
            str(cleanup_output),
            "--manifest-output",
            str(manifest_output),
        ],
    )

    update_manifest.main()

    # The deferred cleanup still receives the full list: the long-gone ghost app
    # plus the current app this release just retired.
    cleanup = json.loads(cleanup_output.read_text())
    assert set(cleanup["app_names"]) == {"ghost-app", "current-app"}

    # The stored manifest no longer tracks the cleaned-up retired apps, so they
    # are not re-listed for cleanup on the next release.
    stored = fake_dict[MANIFEST_DICT_KEY]
    assert stored["retired"] == []
    assert stored["current"]["app_name"] == "frontier-app"
    assert stored["frontier"]["app_name"] == "new-frontier-app"


def test_update_manifest_keeps_retired_when_cleanup_target_none(
    tmp_path, monkeypatch
):
    # cleanup_target: none must preserve retired history (nothing scheduled for
    # cleanup means nothing pruned).
    initial_manifest = {
        "schema_version": 1,
        "current": _app("current-app", us="1.726.0"),
        "frontier": _app("frontier-app", us="1.732.0"),
        "retired": [_app("ghost-app", us="1.691.1")],
    }
    fake_dict = _FakeModalDict({MANIFEST_DICT_KEY: initial_manifest})
    monkeypatch.setattr(
        update_manifest.modal, "Dict", _fake_dict_type(fake_dict)
    )

    config = json.dumps(
        {
            "new_app_target": "none",
            "promote_existing_frontier": False,
            "cleanup_target": "none",
        }
    )
    cleanup_output = tmp_path / "modal-cleanup.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_manifest.py",
            "--config-json",
            config,
            "--modal-environment",
            "testing",
            "--cleanup-output",
            str(cleanup_output),
        ],
    )

    update_manifest.main()

    assert json.loads(cleanup_output.read_text())["app_names"] == []
    stored = fake_dict[MANIFEST_DICT_KEY]
    assert [app["app_name"] for app in stored["retired"]] == ["ghost-app"]
