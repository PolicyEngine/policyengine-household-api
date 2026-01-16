#!/usr/bin/env python3
"""
Check for PolicyEngine package updates and generate PR summary.

This script checks PyPI for newer versions of PolicyEngine packages,
updates setup.py if needed, and generates changelog summaries.
"""

import os
import re
import sys

import requests
import yaml

# Packages to track (US only - UK is updated separately)
PACKAGES = ["policyengine_us"]

# Map package names to GitHub repos
REPO_MAP = {"policyengine_us": "PolicyEngine/policyengine-us"}


def parse_version(version_str):
    """Parse a version string into a tuple of integers."""
    return tuple(map(int, version_str.split(".")))


def get_current_versions(setup_content):
    """Extract current package versions from setup.py content."""
    current_versions = {}
    for pkg in PACKAGES:
        pattern = rf'{pkg.replace("_", "[-_]")}==([0-9]+\.[0-9]+\.[0-9]+)'
        match = re.search(pattern, setup_content)
        if match:
            current_versions[pkg] = match.group(1)
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


def update_setup_content(setup_content, updates):
    """Update setup.py content with new versions."""
    new_content = setup_content
    for pkg, versions in updates.items():
        pattern = rf'({pkg.replace("_", "[-_]")}==)[0-9]+\.[0-9]+\.[0-9]+'
        new_content = re.sub(pattern, rf'\g<1>{versions["new"]}', new_content)
    return new_content


def fetch_changelog(pkg):
    """Fetch changelog from GitHub for a package."""
    repo = REPO_MAP.get(pkg)
    if not repo:
        return None
    url = f"https://raw.githubusercontent.com/{repo}/main/changelog.yaml"
    resp = requests.get(url)
    if resp.status_code == 200:
        return yaml.safe_load(resp.text)
    return None


def get_changes_between_versions(changelog, old_version, new_version):
    """Extract changelog entries between old and new versions."""
    if not changelog:
        return []

    old_v = parse_version(old_version)
    new_v = parse_version(new_version)

    entries_with_versions = []
    current_version = None

    for entry in changelog:
        if "version" in entry:
            current_version = parse_version(entry["version"])
        elif current_version and "bump" in entry:
            bump = entry["bump"]
            major, minor, patch = current_version
            if bump == "major":
                current_version = (major + 1, 0, 0)
            elif bump == "minor":
                current_version = (major, minor + 1, 0)
            elif bump == "patch":
                current_version = (major, minor, patch + 1)

        if current_version:
            entries_with_versions.append((current_version, entry))

    relevant_entries = []
    for version, entry in entries_with_versions:
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
        changelog = fetch_changelog(pkg)
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
    # Read current versions from setup.py
    with open("setup.py", "r") as f:
        setup_content = f.read()

    current_versions = get_current_versions(setup_content)
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

    # Update setup.py
    new_setup_content = update_setup_content(setup_content, updates)
    with open("setup.py", "w") as f:
        f.write(new_setup_content)

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
