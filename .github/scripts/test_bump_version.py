"""Tests for the Towncrier version bump helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def load_bump_version_module():
    module_path = Path(__file__).resolve().parents[1] / "bump_version.py"
    spec = importlib.util.spec_from_file_location(
        "household_api_bump_version",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump_version = load_bump_version_module()


class TestGetCurrentVersion:
    def test_reads_version_from_pyproject(self, tmp_path):
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text('[project]\nversion = "1.2.3"\n')

        assert bump_version.get_current_version(pyproject_path) == "1.2.3"

    def test_raises_when_version_missing(self, tmp_path):
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text('[project]\nname = "demo"\n')

        with pytest.raises(bump_version.VersioningError):
            bump_version.get_current_version(pyproject_path)


class TestInferBump:
    def test_returns_patch_for_changed_and_fixed_fragments(self, tmp_path):
        changelog_dir = tmp_path / "changelog.d"
        changelog_dir.mkdir()
        (changelog_dir / ".gitkeep").write_text("")
        (changelog_dir / "one.changed.md").write_text("Changed.\n")
        (changelog_dir / "two.fixed.md").write_text("Fixed.\n")

        assert bump_version.infer_bump(changelog_dir) == "patch"

    def test_returns_minor_for_added_fragment(self, tmp_path):
        changelog_dir = tmp_path / "changelog.d"
        changelog_dir.mkdir()
        (changelog_dir / "feature.added.md").write_text("Added.\n")

        assert bump_version.infer_bump(changelog_dir) == "minor"

    def test_returns_major_for_breaking_fragment(self, tmp_path):
        changelog_dir = tmp_path / "changelog.d"
        changelog_dir.mkdir()
        (changelog_dir / "feature.breaking.md").write_text("Breaking.\n")

        assert bump_version.infer_bump(changelog_dir) == "major"

    def test_raises_when_no_fragments_exist(self, tmp_path):
        changelog_dir = tmp_path / "changelog.d"
        changelog_dir.mkdir()
        (changelog_dir / ".gitkeep").write_text("")

        with pytest.raises(bump_version.VersioningError):
            bump_version.infer_bump(changelog_dir)


class TestBumpVersion:
    @pytest.mark.parametrize(
        ("version", "bump", "expected"),
        [
            ("1.2.3", "patch", "1.2.4"),
            ("1.2.3", "minor", "1.3.0"),
            ("1.2.3", "major", "2.0.0"),
        ],
    )
    def test_bumps_version(self, version, bump, expected):
        assert bump_version.bump_version(version, bump) == expected


class TestUpdateFile:
    def test_updates_version_in_file(self, tmp_path):
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text('[project]\nversion = "1.2.3"\n')

        updated = bump_version.update_file(pyproject_path, "1.2.3", "1.2.4")

        assert updated is True
        assert 'version = "1.2.4"' in pyproject_path.read_text()

    def test_noop_when_version_not_found(self, tmp_path):
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text('[project]\nversion = "1.2.3"\n')

        updated = bump_version.update_file(pyproject_path, "9.9.9", "1.2.4")

        assert updated is False
        assert 'version = "1.2.3"' in pyproject_path.read_text()


class TestMain:
    def test_updates_temp_project_version(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.2.3"\n'
        )
        changelog_dir = tmp_path / "changelog.d"
        changelog_dir.mkdir()
        (changelog_dir / "feature.added.md").write_text("Added.\n")

        new_version = bump_version.main(tmp_path)

        assert new_version == "1.3.0"
        assert 'version = "1.3.0"' in (tmp_path / "pyproject.toml").read_text()

    def test_exits_with_code_one_when_fragments_missing(
        self, tmp_path, capsys
    ):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.2.3"\n'
        )
        (tmp_path / "changelog.d").mkdir()

        with pytest.raises(SystemExit) as exc_info:
            bump_version.main(tmp_path)

        assert exc_info.value.code == 1
        assert "No changelog fragments found" in capsys.readouterr().err
