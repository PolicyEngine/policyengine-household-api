"""Unit tests for check_updates.py"""

import pytest

from check_updates import (
    find_updates,
    format_changes,
    generate_changelog_entry,
    get_changes_between_versions,
    get_current_versions,
    parse_version,
    update_setup_content,
)


class TestParseVersion:
    def test_simple_version(self):
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_large_numbers(self):
        assert parse_version("10.20.30") == (10, 20, 30)

    def test_zero_version(self):
        assert parse_version("0.0.1") == (0, 0, 1)


class TestGetCurrentVersions:
    def test_extracts_underscore_version(self):
        setup_content = """
install_requires=[
    "policyengine_us==1.2.3",
]
"""
        versions = get_current_versions(setup_content)
        assert versions == {"policyengine_us": "1.2.3"}

    def test_extracts_hyphen_version(self):
        setup_content = """
install_requires=[
    "policyengine-us==4.5.6",
]
"""
        versions = get_current_versions(setup_content)
        assert versions == {"policyengine_us": "4.5.6"}

    def test_no_match_returns_empty(self):
        setup_content = """
install_requires=[
    "some_other_package==1.0.0",
]
"""
        versions = get_current_versions(setup_content)
        assert versions == {}


class TestFindUpdates:
    def test_finds_update_when_versions_differ(self):
        current = {"policyengine_us": "1.0.0"}
        latest = {"policyengine_us": "1.1.0"}
        updates = find_updates(current, latest)
        assert updates == {"policyengine_us": {"old": "1.0.0", "new": "1.1.0"}}

    def test_no_update_when_versions_match(self):
        current = {"policyengine_us": "1.0.0"}
        latest = {"policyengine_us": "1.0.0"}
        updates = find_updates(current, latest)
        assert updates == {}

    def test_handles_missing_package(self):
        current = {}
        latest = {"policyengine_us": "1.0.0"}
        updates = find_updates(current, latest)
        assert updates == {}


class TestUpdateSetupContent:
    def test_updates_version_with_underscore(self):
        setup_content = "policyengine_us==1.0.0"
        updates = {"policyengine_us": {"old": "1.0.0", "new": "2.0.0"}}
        result = update_setup_content(setup_content, updates)
        assert result == "policyengine_us==2.0.0"

    def test_updates_version_with_hyphen(self):
        setup_content = "policyengine-us==1.0.0"
        updates = {"policyengine_us": {"old": "1.0.0", "new": "2.0.0"}}
        result = update_setup_content(setup_content, updates)
        assert result == "policyengine-us==2.0.0"

    def test_preserves_other_content(self):
        setup_content = """install_requires=[
    "flask==2.0.0",
    "policyengine_us==1.0.0",
    "requests==2.28.0",
]"""
        updates = {"policyengine_us": {"old": "1.0.0", "new": "1.5.0"}}
        result = update_setup_content(setup_content, updates)
        assert "flask==2.0.0" in result
        assert "policyengine_us==1.5.0" in result
        assert "requests==2.28.0" in result


class TestGetChangesBetweenVersions:
    def test_returns_empty_for_none_changelog(self):
        result = get_changes_between_versions(None, "1.0.0", "2.0.0")
        assert result == []

    def test_filters_entries_between_versions(self):
        changelog = [
            {"version": "1.0.0", "changes": {"added": ["Initial"]}},
            {"bump": "patch", "changes": {"fixed": ["Bug fix"]}},
            {"bump": "minor", "changes": {"added": ["New feature"]}},
            {"bump": "major", "changes": {"changed": ["Breaking change"]}},
        ]
        # Version progression: 1.0.0 -> 1.0.1 -> 1.1.0 -> 2.0.0
        result = get_changes_between_versions(changelog, "1.0.0", "1.1.0")
        # Should include 1.0.1 and 1.1.0, but not 1.0.0 or 2.0.0
        assert len(result) == 2
        assert result[0]["changes"]["fixed"] == ["Bug fix"]
        assert result[1]["changes"]["added"] == ["New feature"]

    def test_returns_empty_for_same_version(self):
        changelog = [
            {"version": "1.0.0", "changes": {"added": ["Initial"]}},
        ]
        result = get_changes_between_versions(changelog, "1.0.0", "1.0.0")
        assert result == []


class TestFormatChanges:
    def test_formats_all_categories(self):
        entries = [
            {
                "changes": {
                    "added": ["Feature A"],
                    "changed": ["Update B"],
                    "fixed": ["Fix C"],
                    "removed": ["Remove D"],
                }
            }
        ]
        result = format_changes(entries)
        assert "### Added" in result
        assert "- Feature A" in result
        assert "### Changed" in result
        assert "- Update B" in result
        assert "### Fixed" in result
        assert "- Fix C" in result
        assert "### Removed" in result
        assert "- Remove D" in result

    def test_combines_multiple_entries(self):
        entries = [
            {"changes": {"added": ["Feature 1"]}},
            {"changes": {"added": ["Feature 2"]}},
        ]
        result = format_changes(entries)
        assert "- Feature 1" in result
        assert "- Feature 2" in result

    def test_returns_default_for_empty_entries(self):
        result = format_changes([])
        assert result == "No detailed changes available."

    def test_handles_missing_change_categories(self):
        entries = [{"changes": {"added": ["Only added"]}}]
        result = format_changes(entries)
        assert "### Added" in result
        assert "### Changed" not in result
        assert "### Fixed" not in result
        assert "### Removed" not in result


class TestGenerateChangelogEntry:
    def test_generates_correct_format(self):
        updates = {"policyengine_us": {"old": "1.0.0", "new": "1.5.0"}}
        result = generate_changelog_entry(updates)
        assert "- bump: patch" in result
        assert "changes:" in result
        assert "changed:" in result
        assert "Update PolicyEngine US to 1.5.0" in result
