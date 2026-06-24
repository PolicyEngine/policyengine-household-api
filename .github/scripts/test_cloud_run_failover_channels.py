import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parent / "cloud_run_failover_channels.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "cloud_run_failover_channels",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _modal_manifest():
    return {
        "schema_version": 1,
        "current": {
            "app_name": "modal-current",
            "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
            "deployed_at": "2026-06-03T00:00:00+00:00",
        },
        "frontier": {
            "app_name": "modal-frontier",
            "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
            "deployed_at": "2026-06-03T00:00:00+00:00",
        },
        "retired": [],
    }


def test_active_failover_channels_from_modal_manifest():
    module = _load_script_module()

    assert module.active_failover_channels(_modal_manifest()) == [
        {
            "channel": "current",
            "modal_app_name": "modal-current",
            "package_versions": {"uk": "2.31.0", "us": "1.0.0"},
        },
        {
            "channel": "frontier",
            "modal_app_name": "modal-frontier",
            "package_versions": {"uk": "2.88.18", "us": "2.0.0"},
        },
    ]


def test_build_manifest_for_worker_urls_preserves_modal_metadata():
    module = _load_script_module()

    manifest = module.build_manifest_for_worker_urls(
        environment="staging",
        modal_manifest=_modal_manifest(),
        worker_urls={
            "current": "https://current.run.app",
            "frontier": "https://frontier.run.app",
        },
    )

    assert manifest["environment"] == "staging"
    assert manifest["channels"]["current"]["modal_app_name"] == (
        "modal-current"
    )
    assert manifest["channels"]["frontier"]["cloud_run_worker_url"] == (
        "https://frontier.run.app"
    )


def test_build_manifest_for_worker_urls_preserves_retired_metadata():
    module = _load_script_module()
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

    manifest = module.build_manifest_for_worker_urls(
        environment="staging",
        modal_manifest=modal_manifest,
        worker_urls={
            "current": "https://current.run.app",
            "frontier": "https://frontier.run.app",
        },
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


def test_parse_worker_urls_rejects_bad_values():
    module = _load_script_module()

    with pytest.raises(ValueError, match="CHANNEL=URL"):
        module.parse_worker_urls(["current"])

    with pytest.raises(ValueError, match="Unsupported"):
        module.parse_worker_urls(["retired=https://example.com"])

    with pytest.raises(ValueError, match="Duplicate"):
        module.parse_worker_urls(
            [
                "current=https://one.example.com",
                "current=https://two.example.com",
            ]
        )
