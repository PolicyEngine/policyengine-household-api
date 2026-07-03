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

The ``--live-retags`` mode re-reads that channel state at apply time (used by
the retag job, which runs after the slow build job) and emits retags only for
images that are already published, so a release that completes mid-build can
never move a channel tag backward or point it at a not-yet-built image. The
``--print-us-pin`` mode exposes the pyproject pin parser to PR CI so the exact
``policyengine_us==...`` extraction lives in exactly one place.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_GATEWAY_URL = "https://household.api.policyengine.org"
DEFAULT_REPOSITORY = "policyengine/policyengine-household-api"
VERSION_PATTERN = re.compile(r"^[0-9]+(\.[0-9]+)*$")

# Each channel maps to the floating tags it owns; ``current`` also owns its
# documented alias ``latest``. Iteration order is preserved into the emitted
# retag targets.
CHANNEL_TAGS: tuple[tuple[str, list[str]], ...] = (
    ("current", ["current", "latest"]),
    ("frontier", ["frontier"]),
)


class PlanError(Exception):
    """Raised when a valid build/retag plan cannot be produced."""


def main() -> None:
    args = _parse_args()

    if args.print_us_pin:
        pinned_us_version, _ = read_pyproject_versions(Path(args.pyproject))
        print(pinned_us_version)
        return

    if args.live_retags:
        _emit_live_retags(args)
        return

    if not args.mode:
        raise PlanError(
            "--mode is required unless --print-us-pin or --live-retags is set"
        )

    sync_channels = should_sync_channels(args.mode, args.sync_channel_tags)

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

    _write_outputs(
        args.github_output,
        {
            "builds": json.dumps(plan["builds"]),
            "retags": json.dumps(plan["retags"]),
            "has_builds": "true" if plan["builds"] else "false",
            "has_retags": "true" if plan["retags"] else "false",
        },
    )
    print(json.dumps(plan, indent=2))


def should_sync_channels(mode: str, sync_channel_tags: bool) -> bool:
    """Whether to repoint channel tags: always on release, opt-in otherwise."""
    return mode == "release" or sync_channel_tags


def build_plan(
    *,
    mode: str,
    pinned_us_version: str | None = None,
    api_version: str | None = None,
    head_sha: str | None = None,
    requested_us_version: str | None = None,
    channel_versions: dict[str, str | None] | None = None,
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
        targets_by_version = _channel_targets_by_version(channel_versions)
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


def plan_live_retags(
    *,
    channel_versions: dict[str, str | None],
    existing_tags: set[str],
) -> tuple[list[dict], list[dict]]:
    """Recompute channel retags from live gateway state at apply time.

    Returns ``(retags, skipped)``. A retag is emitted only when the channel's
    exact-version image is already published; a channel whose image is not yet
    built is returned in ``skipped`` so the retag job never moves a tag
    backward or points it at a missing image. The serialized follow-up publish
    run (or a manual rebuild) publishes the image and repoints the tag.
    """
    retags: list[dict] = []
    skipped: list[dict] = []
    targets_by_version = _channel_targets_by_version(channel_versions)
    for version, targets in targets_by_version.items():
        exact_tag = f"us-{version}"
        if exact_tag in existing_tags:
            retags.append({"source": exact_tag, "targets": targets})
        else:
            skipped.append({"version": version, "targets": targets})
    return retags, skipped


def _channel_targets_by_version(
    channel_versions: dict[str, str | None],
) -> dict[str, list[str]]:
    """Group floating tags by the exact ``us-<version>`` they point at.

    Validates each channel version and fails with a clear ``PlanError`` when
    the gateway omits a channel or reports an empty version, rather than
    letting a ``KeyError`` escape as a raw traceback.
    """
    targets_by_version: dict[str, list[str]] = {}
    missing: list[str] = []
    for channel, extra_tags in CHANNEL_TAGS:
        version = channel_versions.get(channel)
        if not version:
            missing.append(channel)
            continue
        _require_valid_version(version)
        targets_by_version.setdefault(version, []).extend(extra_tags)
    if missing:
        raise PlanError(
            "gateway /versions/us reported no version for channel(s): "
            + ", ".join(missing)
        )
    return targets_by_version


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


def fetch_channel_versions(gateway_url: str) -> dict[str, str | None]:
    """Read live channel versions from the gateway ``/versions/us`` endpoint.

    A channel whose app reference is unset is omitted from the payload; reading
    with ``.get`` keeps that case as ``None`` so it surfaces as a clean
    ``PlanError`` downstream instead of a ``KeyError``.
    """
    payload = _fetch_json(f"{gateway_url}/versions/us")
    return {
        "current": payload.get("current"),
        "frontier": payload.get("frontier"),
    }


def fetch_existing_tags(repository: str) -> set[str]:
    """List existing GHCR tags via the anonymous pull-scope registry API.

    Assumes the package is public (the publish workflow grants no
    ``packages: read``). A never-pushed or deleted package has no tags list, so
    a 404 is treated as an empty set rather than crashing the plan job, letting
    the first publish backfill cleanly.
    """
    token_payload = _fetch_json(
        "https://ghcr.io/token?scope="
        + urllib.parse.quote(f"repository:{repository}:pull", safe=":")
    )
    headers = {"Authorization": f"Bearer {token_payload['token']}"}
    tags: set[str] = set()
    url = f"https://ghcr.io/v2/{repository}/tags/list?n=1000"
    while url:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
                link_header = response.headers.get("Link", "")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return set()
            raise
        tags.update(payload.get("tags") or [])
        url = _next_page_url(link_header)
    return tags


def _emit_live_retags(args: argparse.Namespace) -> None:
    """Recompute retags from live channel state for the retag job."""
    channel_versions = fetch_channel_versions(args.gateway_url)
    existing_tags = fetch_existing_tags(args.repository)
    retags, skipped = plan_live_retags(
        channel_versions=channel_versions, existing_tags=existing_tags
    )
    for entry in skipped:
        targets = ", ".join(entry["targets"])
        print(
            f"::warning::live channel state wants {targets} -> "
            f"us-{entry['version']}, but that image is not published yet; "
            "leaving those tags unchanged (a later run repoints them)",
            file=sys.stderr,
        )
    _write_outputs(
        args.github_output,
        {
            "retags": json.dumps(retags),
            "has_retags": "true" if retags else "false",
        },
    )
    print(json.dumps({"retags": retags, "skipped": skipped}, indent=2))


def _write_outputs(github_output: str | None, outputs: dict[str, str]) -> None:
    if not github_output:
        return
    with Path(github_output).open("a") as output_file:
        for key, value in outputs.items():
            output_file.write(f"{key}={value}\n")


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


def parse_bool_flag(value: str) -> bool:
    """Parse a workflow string boolean (``'true'``/``'false'``) to ``bool``."""
    return value.lower() == "true"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan GHCR Docker image builds and channel-tag updates."
    )
    parser.add_argument("--mode", choices=["release", "dispatch"])
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--requested-us-version", default="")
    parser.add_argument(
        "--sync-channel-tags",
        default="false",
        help="'true' to repoint current/frontier/latest (dispatch mode only;"
        " release mode always syncs)",
    )
    parser.add_argument(
        "--live-retags",
        action="store_true",
        help="Recompute channel retags from live gateway state, emitting only"
        " retags whose target image is already published; used by the retag"
        " job after builds finish.",
    )
    parser.add_argument(
        "--print-us-pin",
        action="store_true",
        help="Print the pinned policyengine-us version from pyproject.toml and"
        " exit (shared with PR Docker build CI).",
    )
    parser.add_argument("--pyproject", default="libs/household-api/pyproject.toml")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    args.sync_channel_tags = parse_bool_flag(args.sync_channel_tags)
    return args


if __name__ == "__main__":
    try:
        main()
    except PlanError as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
