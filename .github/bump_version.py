"""Infer semver bump from towncrier fragment types and update version."""

from __future__ import annotations

import re
import sys
from pathlib import Path


class VersioningError(Exception):
    """Raised when version bump inference cannot be completed."""


def get_current_version(pyproject_path: Path) -> str:
    text = pyproject_path.read_text()
    match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    if not match:
        raise VersioningError("Could not find version in pyproject.toml")
    return match.group(1)


def get_fragment_category(fragment_path: Path) -> str | None:
    parts = fragment_path.name.split(".")
    if len(parts) >= 3:
        return parts[-2]
    if fragment_path.suffix and fragment_path.suffix != ".md":
        return fragment_path.suffix.lstrip(".")
    return None


def infer_bump(changelog_dir: Path) -> str:
    fragments = [
        fragment
        for fragment in changelog_dir.iterdir()
        if fragment.is_file() and fragment.name != ".gitkeep"
    ]
    if not fragments:
        raise VersioningError("No changelog fragments found")

    categories = {
        category
        for fragment in fragments
        if (category := get_fragment_category(fragment))
    }

    if "breaking" in categories:
        return "major"
    if "added" in categories or "removed" in categories:
        return "minor"
    return "patch"


def bump_version(version: str, bump: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def update_file(path: Path, old_version: str, new_version: str) -> bool:
    text = path.read_text()
    updated = text.replace(
        f'version = "{old_version}"',
        f'version = "{new_version}"',
    )
    if updated == text:
        return False
    path.write_text(updated)
    print(f"  Updated {path}")
    return True


def main(root: Path | None = None) -> str:
    root = root or Path(__file__).resolve().parent.parent
    pyproject = root / "pyproject.toml"
    changelog_dir = root / "changelog.d"

    try:
        current = get_current_version(pyproject)
        bump = infer_bump(changelog_dir)
    except VersioningError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    new = bump_version(current, bump)
    print(f"Version: {current} -> {new} ({bump})")
    update_file(pyproject, current, new)
    return new


if __name__ == "__main__":
    raise SystemExit(main())
