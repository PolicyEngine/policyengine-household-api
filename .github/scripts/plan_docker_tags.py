"""Plan GHCR image builds and channel-tag updates for the publish workflow.

Emits two GitHub Actions outputs:

- ``builds``: JSON list of ``{"us_version": ..., "tags": ...}`` entries
  (``tags`` is a space-separated list of bare tag names) to build with the
  ``POLICYENGINE_US_VERSION`` build arg.
- ``retags``: JSON list of ``{"source": ..., "targets": [...]}`` entries that
  repoint floating channel tags (``current``/``frontier``/``latest``) at
  already-published exact-version images, mirroring how Modal promotes a
  frontier worker to current without redeploying it.

Channel state is read from the live gateway ``/versions/us`` endpoint, the
source of truth for what the hosted API serves, so code-only releases and
manual Modal releases stay in sync automatically.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_GATEWAY_URL = "https://household.api.policyengine.org"
DEFAULT_REPOSITORY = "policyengine/policyengine-household-api"
VERSION_PATTERN = re.compile(r"^[0-9]+(\.[0-9]+)*$")


class PlanError(Exception):
    """Raised when a valid build/retag plan cannot be produced."""


def main() -> None:
    args = _parse_args()
    sync_channels = args.mode == "release" or args.sync_channel_tags

    pinned_us_version = None
    api_version = None
    if args.mode == "release":
        pinned_us_version, api_version = read_pyproject_versions(
            Path(args.pyproject)
        )

    channel_versions = None
    existing_tags: set[str] = set()
    if sync_channels:
        channel_versions = fetch_channel_versions(args.gateway_url)
        existing_tags = fetch_existing_tags(args.repository)

    plan = build_plan(
        mode=args.mode,
        pinned_us_version=pinned_us_version,
        api_version=api_version,
        head_sha=args.head_sha,
        requested_us_version=args.requested_us_version or None,
        channel_versions=channel_versions,
        existing_tags=existing_tags,
    )

    outputs = {
        "builds": json.dumps(plan["builds"]),
        "retags": json.dumps(plan["retags"]),
        "has_builds": "true" if plan["builds"] else "false",
        "has_retags": "true" if plan["retags"] else "false",
    }
    if args.github_output:
        with Path(args.github_output).open("a") as output_file:
            for key, value in outputs.items():
                output_file.write(f"{key}={value}\n")
    print(json.dumps(plan, indent=2))


def build_plan(
    *,
    mode: str,
    pinned_us_version: str | None = None,
    api_version: str | None = None,
    head_sha: str | None = None,
    requested_us_version: str | None = None,
    channel_versions: dict[str, str] | None = None,
    existing_tags: set[str] | None = None,
) -> dict:
    """Pure planning logic; all network/file state is passed in."""
    existing_tags = existing_tags or set()
    builds: list[dict] = []
    retags: list[dict] = []
    planned_versions: set[str] = set()

    if mode == "release":
        if not (pinned_us_version and api_version and head_sha):
            raise PlanError(
                "release mode requires the pyproject pin, the project "
                "version, and the release commit sha"
            )
        _require_valid_version(pinned_us_version)
        tags = [f"us-{pinned_us_version}", api_version, f"sha-{head_sha}"]
        builds.append(
            {"us_version": pinned_us_version, "tags": " ".join(tags)}
        )
        planned_versions.add(pinned_us_version)
    elif mode == "dispatch":
        if not requested_us_version and channel_versions is None:
            raise PlanError(
                "dispatch mode needs a policyengine-us version to publish, "
                "channel-tag syncing, or both"
            )
        if requested_us_version:
            _require_valid_version(requested_us_version)
            builds.append(
                {
                    "us_version": requested_us_version,
                    "tags": f"us-{requested_us_version}",
                }
            )
            planned_versions.add(requested_us_version)
    else:
        raise PlanError(f"unknown mode: {mode}")

    if channel_versions is not None:
        targets_by_version: dict[str, list[str]] = {}
        for channel, extra_tags in (
            ("current", ["current", "latest"]),
            ("frontier", ["frontier"]),
        ):
            version = channel_versions.get(channel)
            if not version:
                raise PlanError(
                    f"gateway reported no {channel} channel version"
                )
            _require_valid_version(version)
            targets_by_version.setdefault(version, []).extend(extra_tags)
        for version, targets in targets_by_version.items():
            exact_tag = f"us-{version}"
            needs_backfill = (
                exact_tag not in existing_tags
                and version not in planned_versions
            )
            if needs_backfill:
                builds.append({"us_version": version, "tags": exact_tag})
                planned_versions.add(version)
            retags.append({"source": exact_tag, "targets": targets})

    return {"builds": builds, "retags": retags}


def read_pyproject_versions(pyproject_path: Path) -> tuple[str, str]:
    """Return (policyengine-us pin, project version) from pyproject.toml."""
    data = tomllib.loads(pyproject_path.read_text())
    api_version = data["project"]["version"]
    for dependency in data["project"]["dependencies"]:
        requirement = dependency.replace(" ", "")
        name, _, version = requirement.partition("==")
        if name.replace("-", "_") == "policyengine_us" and version:
            return version, api_version
    raise PlanError("no exact policyengine_us pin found in pyproject.toml")


def fetch_channel_versions(gateway_url: str) -> dict[str, str]:
    payload = _fetch_json(f"{gateway_url}/versions/us")
    return {
        "current": payload["current"],
        "frontier": payload["frontier"],
    }


def fetch_existing_tags(repository: str) -> set[str]:
    """List existing GHCR tags via the anonymous pull-scope registry API."""
    token_payload = _fetch_json(
        "https://ghcr.io/token?scope="
        + urllib.parse.quote(f"repository:{repository}:pull", safe=":")
    )
    headers = {"Authorization": f"Bearer {token_payload['token']}"}
    tags: set[str] = set()
    url = f"https://ghcr.io/v2/{repository}/tags/list?n=1000"
    while url:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
            link_header = response.headers.get("Link", "")
        tags.update(payload.get("tags") or [])
        url = _next_page_url(link_header)
    return tags


def _next_page_url(link_header: str) -> str | None:
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    if not match:
        return None
    return urllib.parse.urljoin("https://ghcr.io", match.group(1))


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def _require_valid_version(version: str) -> None:
    if not VERSION_PATTERN.match(version):
        raise PlanError(f"invalid package version: {version!r}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan GHCR Docker image builds and channel-tag updates."
    )
    parser.add_argument(
        "--mode", choices=["release", "dispatch"], required=True
    )
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--requested-us-version", default="")
    parser.add_argument(
        "--sync-channel-tags",
        default="false",
        help="'true' to repoint current/frontier/latest (dispatch mode only;"
        " release mode always syncs)",
    )
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    args.sync_channel_tags = args.sync_channel_tags.lower() == "true"
    return args


if __name__ == "__main__":
    try:
        main()
    except PlanError as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
