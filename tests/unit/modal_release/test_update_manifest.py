import json
import sys

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


def test_update_manifest_emits_cleanup_without_pruning(tmp_path, monkeypatch):
    # The deploy job must NOT prune retired apps: pruning happens only after the
    # deferred cleanup job confirms the stop succeeded (see prune_manifest.py).
    initial_manifest = {
        "schema_version": 1,
        "current": _app("current-app", us="1.726.0"),
        "frontier": _app("frontier-app", us="1.732.0"),
        # A long-since-deleted app still tracked in the retired history.
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
        ],
    )

    update_manifest.main()

    # The cleanup list carries the long-gone ghost app plus the current app this
    # release just retired.
    cleanup = json.loads(cleanup_output.read_text())
    assert set(cleanup["app_names"]) == {"ghost-app", "current-app"}

    # The stored manifest still tracks those retired apps; nothing is pruned
    # until the cleanup job confirms the stop.
    stored = fake_dict[MANIFEST_DICT_KEY]
    assert {app["app_name"] for app in stored["retired"]} == {
        "ghost-app",
        "current-app",
    }
    assert stored["current"]["app_name"] == "frontier-app"
    assert stored["frontier"]["app_name"] == "new-frontier-app"
