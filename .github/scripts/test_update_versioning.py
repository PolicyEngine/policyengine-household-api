"""Tests for the release versioning workflow helper."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path


def load_update_versioning_module():
    module_path = Path(__file__).resolve().parent / "update_versioning.py"
    spec = importlib.util.spec_from_file_location(
        "household_api_update_versioning",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_versioning = load_update_versioning_module()


def write_test_project(
    root: Path, fragment_name: str, fragment_body: str
) -> None:
    (root / "changelog.d").mkdir()
    (root / "changelog.d" / fragment_name).write_text(fragment_body)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "All notable changes to this project will be documented in this file.\n\n"
        "## [1.2.3] - 2026-01-01 00:00:00\n\n"
        "### Changed\n\n"
        "- Legacy entry.\n"
    )
    (root / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "1.2.3"

[tool.towncrier]
package = "demo"
directory = "changelog.d"
filename = "CHANGELOG.md"
title_format = "## [{version}] - {project_date}"
issue_format = ""
underlines = ["", "", ""]

[[tool.towncrier.type]]
directory = "breaking"
name = "Breaking changes"
showcontent = true

[[tool.towncrier.type]]
directory = "added"
name = "Added"
showcontent = true

[[tool.towncrier.type]]
directory = "changed"
name = "Changed"
showcontent = true

[[tool.towncrier.type]]
directory = "fixed"
name = "Fixed"
showcontent = true

[[tool.towncrier.type]]
directory = "removed"
name = "Removed"
showcontent = true
""".strip()
        + "\n"
    )


def test_update_versioning_builds_release_and_preserves_legacy_changelog(
    tmp_path,
):
    write_test_project(
        tmp_path,
        "feature.added.md",
        "Add a new staging deployment safeguard.\n",
    )

    new_version = update_versioning.update_versioning(tmp_path)

    assert new_version == "1.3.0"
    assert 'version = "1.3.0"' in (tmp_path / "pyproject.toml").read_text()

    changelog = (tmp_path / "CHANGELOG.md").read_text()
    assert re.match(r"## \[1\.3\.0\] - \d{4}-\d{2}-\d{2}", changelog)
    assert "### Added" in changelog
    assert "- Add a new staging deployment safeguard." in changelog
    assert "# Changelog" in changelog
    assert "- Legacy entry." in changelog
    assert changelog.index("# Changelog") > changelog.index(
        "- Add a new staging deployment safeguard."
    )
    assert not (tmp_path / "changelog.d" / "feature.added.md").exists()
