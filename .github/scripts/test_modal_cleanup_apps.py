from __future__ import annotations

import os
import subprocess


def test_modal_cleanup_treats_already_stopped_app_as_success(tmp_path):
    cleanup_file = tmp_path / "cleanup.json"
    cleanup_file.write_text('{"app_names":["old-app"]}\n')
    _write_fake_uv(tmp_path, exit_code=1, output="App is already stopped.")

    result = subprocess.run(
        [
            "bash",
            ".github/scripts/modal-cleanup-apps.sh",
            str(cleanup_file),
        ],
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "MODAL_ENVIRONMENT": "testing",
        },
        text=True,
    )

    assert result.returncode == 0
    assert "already stopped" in result.stdout


def test_modal_cleanup_fails_on_other_stop_errors(tmp_path):
    cleanup_file = tmp_path / "cleanup.json"
    cleanup_file.write_text('{"app_names":["old-app"]}\n')
    _write_fake_uv(tmp_path, exit_code=1, output="Permission denied.")

    result = subprocess.run(
        [
            "bash",
            ".github/scripts/modal-cleanup-apps.sh",
            str(cleanup_file),
        ],
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "MODAL_ENVIRONMENT": "testing",
        },
        text=True,
    )

    assert result.returncode == 1
    assert "Permission denied" in result.stdout


def _write_fake_uv(tmp_path, *, exit_code: int, output: str) -> None:
    uv = tmp_path / "uv"
    uv.write_text(
        f"""#!/usr/bin/env bash
echo "{output}" >&2
exit {exit_code}
"""
    )
    uv.chmod(0o755)
