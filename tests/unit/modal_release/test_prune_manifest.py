import json
import sys

import pytest

from policyengine_household_modal import prune_manifest
from policyengine_household_common.release_manifest import MANIFEST_DICT_KEY


def _app(name, *, uk="2.31.0", us="1.691.1"):
    return {
        "app_name": name,
        "package_versions": {"uk": uk, "us": us},
        "deployed_at": "2026-01-01T00:00:00+00:00",
    }


class _FakeModalDict:
    def __init__(self, initial):
        self._store = dict(initial)
        self.set_calls = 0

    def get(self, key, default=None):
        return self._store.get(key, default)

    def __getitem__(self, key):
        return self._store[key]

    def __setitem__(self, key, value):
        self.set_calls += 1
        self._store[key] = value


def _fake_dict_type(instance):
    class _FakeDictType:
        @classmethod
        def from_name(cls, *args, **kwargs):
            assert kwargs["create_if_missing"] is False
            return instance

    return _FakeDictType


def _cleanup_json(tmp_path, cleanup_payload):
    cleanup_json = tmp_path / "modal-cleanup.json"
    cleanup_json.write_text(json.dumps(cleanup_payload))
    return cleanup_json


def _run(monkeypatch, fake_dict, cleanup_payload, tmp_path):
    monkeypatch.setattr(
        prune_manifest.modal, "Dict", _fake_dict_type(fake_dict)
    )
    cleanup_json = _cleanup_json(tmp_path, cleanup_payload)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prune_manifest.py",
            "--cleanup-json",
            str(cleanup_json),
            "--modal-environment",
            "testing",
        ],
    )
    assert prune_manifest.main() == 0


def test_prune_manifest_removes_cleaned_apps(tmp_path, monkeypatch):
    fake_dict = _FakeModalDict(
        {
            MANIFEST_DICT_KEY: {
                "schema_version": 1,
                "current": _app("current-app"),
                "frontier": _app("frontier-app"),
                "retired": [_app("ghost-app"), _app("recent-app")],
            }
        }
    )

    _run(
        monkeypatch,
        fake_dict,
        {"app_names": ["ghost-app", "recent-app"]},
        tmp_path,
    )

    stored = fake_dict[MANIFEST_DICT_KEY]
    assert stored["retired"] == []
    # Active channels are untouched.
    assert stored["current"]["app_name"] == "current-app"
    assert stored["frontier"]["app_name"] == "frontier-app"


def test_prune_manifest_keeps_unlisted_retired(tmp_path, monkeypatch):
    fake_dict = _FakeModalDict(
        {
            MANIFEST_DICT_KEY: {
                "schema_version": 1,
                "current": _app("current-app"),
                "frontier": _app("frontier-app"),
                "retired": [_app("ghost-app"), _app("keep-app")],
            }
        }
    )

    _run(monkeypatch, fake_dict, {"app_names": ["ghost-app"]}, tmp_path)

    stored = fake_dict[MANIFEST_DICT_KEY]
    assert [app["app_name"] for app in stored["retired"]] == ["keep-app"]


def test_prune_manifest_noop_when_cleanup_list_empty(tmp_path, monkeypatch):
    fake_dict = _FakeModalDict(
        {
            MANIFEST_DICT_KEY: {
                "schema_version": 1,
                "current": _app("current-app"),
                "frontier": _app("frontier-app"),
                "retired": [_app("ghost-app")],
            }
        }
    )

    _run(monkeypatch, fake_dict, {"app_names": []}, tmp_path)

    # No manifest write at all when there is nothing to prune.
    assert fake_dict.set_calls == 0
    assert [
        app["app_name"] for app in fake_dict[MANIFEST_DICT_KEY]["retired"]
    ] == ["ghost-app"]


def test_prune_manifest_refuses_missing_manifest(
    tmp_path, monkeypatch, capsys
):
    class _MissingManifestError(Exception):
        pass

    class _MissingDictType:
        @classmethod
        def from_name(cls, *args, **kwargs):
            assert kwargs["create_if_missing"] is False
            raise _MissingManifestError()

    cleanup_json = _cleanup_json(tmp_path, {"app_names": ["ghost-app"]})
    monkeypatch.setattr(prune_manifest.modal, "Dict", _MissingDictType)
    monkeypatch.setattr(prune_manifest, "NotFoundError", _MissingManifestError)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prune_manifest.py",
            "--cleanup-json",
            str(cleanup_json),
            "--modal-environment",
            "testing",
        ],
    )

    assert prune_manifest.main() == 1
    assert "refusing to prune" in capsys.readouterr().err


def test_prune_manifest_requires_modal_environment(
    tmp_path, monkeypatch, capsys
):
    cleanup_json = _cleanup_json(tmp_path, {"app_names": ["ghost-app"]})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prune_manifest.py",
            "--cleanup-json",
            str(cleanup_json),
        ],
    )

    with pytest.raises(SystemExit) as error:
        prune_manifest.main()

    assert error.value.code == 2
    assert "--modal-environment" in capsys.readouterr().err
