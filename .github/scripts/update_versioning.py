#!/usr/bin/env python3
"""Run the version bump and changelog build steps for releases."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUMP_VERSION_SCRIPT = ROOT / ".github" / "bump_version.py"


def load_bump_version_module(script_path: Path = BUMP_VERSION_SCRIPT):
    spec = importlib.util.spec_from_file_location("bump_version", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Could not load bump version script: {script_path}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_changelog(project_root: Path, version: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "towncrier",
            "build",
            "--yes",
            "--version",
            version,
        ],
        cwd=project_root,
        check=True,
    )


def update_versioning(project_root: Path = ROOT) -> str:
    bump_version = load_bump_version_module()
    new_version = bump_version.main(project_root)
    build_changelog(project_root, new_version)
    return new_version


def main() -> int:
    version = update_versioning()
    print(f"Built changelog for {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
