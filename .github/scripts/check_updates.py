#!/usr/bin/env python3
"""
Check for PolicyEngine package updates and generate PR summary.

This script checks PyPI for newer versions of PolicyEngine packages,
updates pyproject.toml if needed, and generates changelog summaries.
"""

import os
import re
import sys
import tomllib

import requests

# Packages to track (US only - UK is updated separately)
PACKAGES = ["policyengine_us"]

# Map package names to GitHub repos
REPO_MAP = {"policyengine_us": "PolicyEngine/policyengine-us"}


def parse_version(version_str):
    """Parse a version string into a tuple of integers."""
    return tuple(map(int, version_str.split(".")))


def get_current_versions(pyproject_content):
    """Extract current package versions from pyproject.toml content."""
    current_versions = {}
    dependencies = tomllib.loads(pyproject_content)["project"].get(
        "dependencies", []
    )
    for pkg in PACKAGES:
        package_names = (pkg, pkg.replace("_", "-"))
        for dependency in dependencies:
            for package_name in package_names:
                if dependency.startswith(f"{package_name}=="):
                    current_versions[pkg] = dependency.split("==", 1)[1]
                    break
            if pkg in current_versions:
                break
    return current_versions


def get_latest_versions():
    """Fetch latest versions from PyPI for all tracked packages."""
    latest_versions = {}
    for pkg in PACKAGES:
        pypi_name = pkg.replace("_", "-")
        resp = requests.get(f"https://pypi.org/pypi/{pypi_name}/json")
        if resp.status_code == 200:
            latest_versions[pkg] = resp.json()["info"]["version"]
    return latest_versions


def find_updates(current_versions, latest_versions):
    """Compare current and latest versions to find updates."""
    updates = {}
    for pkg in PACKAGES:
        if pkg in current_versions and pkg in latest_versions:
            if current_versions[pkg] != latest_versions[pkg]:
                updates[pkg] = {
                    "old": current_versions[pkg],
                    "new": latest_versions[pkg],
                }
    return updates


def update_pyproject_content(pyproject_content, updates):
    """Update pyproject.toml content with new versions."""
    new_content = pyproject_content
    for pkg, versions in updates.items():
        pattern = (
            rf'("{pkg.replace("_", "[-_]")}==)'
            rf'{re.escape(versions["old"])}(")'
        )
        new_content = re.sub(
            pattern,
            rf"\g<1>{versions['new']}\g<2>",
            new_content,
        )
    return new_content


def fetch_changelog(pkg):
    """Fetch changelog from GitHub for a package."""
    repo = REPO_MAP.get(pkg)
    if not repo:
        return None
    url = f"https://raw.githubusercontent.com/{repo}/main/CHANGELOG.md"
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.text
    return None


def parse_changelog_md(text):
    """Parse a Keep a Changelog markdown file into structured entries.

    Returns a list of dicts like:
        [{"version": "1.2.3", "changes": {"added": [...], "fixed": [...]}}, ...]
    """
    if not text:
        return []

    entries = []
    current_entry = None
    current_category = None

    for line in text.splitlines():
        # Match version heading: ## [1.2.3] - 2024-01-01
        version_match = re.match(r"^##\s+\[(\d+\.\d+\.\d+)\]", line)
        if version_match:
            current_entry = {
                "version": version_match.group(1),
                "changes": {},
            }
            entries.append(current_entry)
            current_category = None
            continue

        if current_entry is None:
            continue

        # Match category heading: ### Added, ### Changed, etc.
        category_match = re.match(r"^###\s+(\w+)", line)
        if category_match:
            current_category = category_match.group(1).lower()
            continue

        # Match list item: - Some change description
        item_match = re.match(r"^-\s+(.+)", line)
        if item_match and current_category:
            current_entry["changes"].setdefault(current_category, [])
            current_entry["changes"][current_category].append(
                item_match.group(1)
            )

    return entries


def get_changes_between_versions(changelog, old_version, new_version):
    """Extract changelog entries between old and new versions."""
    if not changelog:
        return []

    old_v = parse_version(old_version)
    new_v = parse_version(new_version)

    relevant_entries = []
    for entry in changelog:
        if "version" not in entry:
            continue
        version = parse_version(entry["version"])
        if old_v < version <= new_v:
            relevant_entries.append(entry)

    return relevant_entries


def format_changes(entries):
    """Format changelog entries as markdown."""
    added = []
    changed = []
    fixed = []
    removed = []

    for entry in entries:
        changes = entry.get("changes", {})
        added.extend(changes.get("added", []))
        changed.extend(changes.get("changed", []))
        fixed.extend(changes.get("fixed", []))
        removed.extend(changes.get("removed", []))

    sections = []
    if added:
        sections.append(
            "### Added\n" + "\n".join(f"- {item}" for item in added)
        )
    if changed:
        sections.append(
            "### Changed\n" + "\n".join(f"- {item}" for item in changed)
        )
    if fixed:
        sections.append(
            "### Fixed\n" + "\n".join(f"- {item}" for item in fixed)
        )
    if removed:
        sections.append(
            "### Removed\n" + "\n".join(f"- {item}" for item in removed)
        )

    return (
        "\n\n".join(sections) if sections else "No detailed changes available."
    )


def generate_summary(updates):
    """Generate PR summary with version table and changelogs."""
    summary_parts = []

    # Version table
    version_table = "| Package | Old Version | New Version |\n|---------|-------------|-------------|\n"
    for pkg, versions in updates.items():
        version_table += f"| {pkg} | {versions['old']} | {versions['new']} |\n"
    summary_parts.append(version_table)

    # Changelog for each package
    for pkg, versions in updates.items():
        changelog_text = fetch_changelog(pkg)
        changelog = (
            parse_changelog_md(changelog_text) if changelog_text else None
        )
        if changelog:
            entries = get_changes_between_versions(
                changelog, versions["old"], versions["new"]
            )
            if entries:
                formatted = format_changes(entries)
                summary_parts.append(
                    f"## What Changed ({pkg} {versions['old']} → {versions['new']})\n\n{formatted}"
                )
            else:
                summary_parts.append(
                    f"## What Changed ({pkg} {versions['old']} → {versions['new']})\n\nNo changelog entries found between these versions."
                )

    return "\n\n".join(summary_parts)


def generate_changelog_entry(updates):
    """Generate changelog entry for this repo."""
    new_version = updates["policyengine_us"]["new"]
    return f"""- bump: patch
  changes:
    changed:
    - Update PolicyEngine US to {new_version}
"""


def write_github_output(key, value):
    """Write output to GitHub Actions output file."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")


def main():
    """Main entry point for the script."""
    # Read current versions from pyproject.toml
    with open("pyproject.toml", "r") as f:
        pyproject_content = f.read()

    current_versions = get_current_versions(pyproject_content)
    print(f"Current versions: {current_versions}")

    # Get latest versions from PyPI
    latest_versions = get_latest_versions()
    print(f"Latest versions: {latest_versions}")

    # Check for updates
    updates = find_updates(current_versions, latest_versions)

    if not updates:
        print("No updates available.")
        write_github_output("has_updates", "false")
        return 0

    print(f"Updates available: {updates}")

    # Update pyproject.toml
    new_pyproject_content = update_pyproject_content(
        pyproject_content, updates
    )
    with open("pyproject.toml", "w") as f:
        f.write(new_pyproject_content)

    # Generate and save PR summary
    full_summary = generate_summary(updates)
    with open("pr_summary.md", "w") as f:
        f.write(full_summary)

    # Create changelog entry
    changelog_entry = generate_changelog_entry(updates)
    with open("changelog_entry.yaml", "w") as f:
        f.write(changelog_entry)

    # Set outputs
    write_github_output("has_updates", "true")
    updates_str = ", ".join(
        f"{pkg} to {v['new']}" for pkg, v in updates.items()
    )
    write_github_output("updates_summary", updates_str)

    print("Updates prepared successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
