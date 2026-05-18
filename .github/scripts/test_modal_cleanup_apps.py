from __future__ import annotations

import os
import subprocess


def test_modal_cleanup_confirms_app_stop_in_noninteractive_ci(tmp_path):
    cleanup_file = tmp_path / "cleanup.json"
    cleanup_file.write_text('{"app_names":["old-app"]}\n')
    args_file = tmp_path / "uv-args.txt"
    _write_fake_uv(
        tmp_path,
        exit_code=0,
        output="Stopped.",
        args_file=args_file,
    )

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
    assert args_file.read_text().splitlines() == [
        "run",
        "modal",
        "app",
        "stop",
        "--yes",
        "--env",
        "testing",
        "old-app",
    ]


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


def _write_fake_uv(
    tmp_path,
    *,
    exit_code: int,
    output: str,
    args_file=None,
) -> None:
    uv = tmp_path / "uv"
    args_capture = (
        f"""printf '%s\\n' "$@" > "{args_file}"
"""
        if args_file is not None
        else ""
    )
    uv.write_text(
        f"""#!/usr/bin/env bash
{args_capture}\
echo "{output}" >&2
exit {exit_code}
"""
    )
    uv.chmod(0o755)
