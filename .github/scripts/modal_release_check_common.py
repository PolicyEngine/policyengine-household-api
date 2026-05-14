from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def event_pr_body(event_path: str) -> str | None:
    event = json.loads(Path(event_path).read_text())
    return (event.get("pull_request") or {}).get("body")


def get_changed_files(base_ref: str | None) -> list[str]:
    base_ref = base_ref or os.getenv("GITHUB_BASE_REF") or "main"
    commands = [
        ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
    ]

    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            continue
        return [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]

    raise RuntimeError(f"Unable to determine changed files from {base_ref}")


def parse_changed_files_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--base-ref")
    return parser.parse_args()


def parse_pr_body_check_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--event-path",
        default=os.getenv("GITHUB_EVENT_PATH"),
        required=os.getenv("GITHUB_EVENT_PATH") is None,
    )
    parser.add_argument("--base-ref")
    return parser.parse_args()
