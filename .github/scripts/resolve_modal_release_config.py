from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.request import Request, urlopen

from policyengine_household_api.modal_release.release_config import (
    ModalReleaseConfig,
    ModalReleaseConfigError,
    body_contains_modal_release_config,
    default_weekly_config,
    parse_modal_release_config_from_body,
    release_config_to_dict,
)


WEEKLY_UPDATE_COMMIT_MESSAGE = "Update PolicyEngine Household API"


@dataclass(frozen=True)
class ResolvedModalRelease:
    should_deploy: bool
    source: str
    deploy_mode: str
    config: ModalReleaseConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "should_deploy": self.should_deploy,
            "source": self.source,
            "deploy_mode": self.deploy_mode,
            "config": None,
        }
        if self.config:
            data["config"] = release_config_to_dict(self.config)
        return data


def main() -> int:
    args = _parse_args()
    event = json.loads(Path(args.event_path).read_text())

    try:
        resolved = resolve_release_from_event(
            event,
            fetch_pr_body_for_commit=fetch_pr_body_for_commit,
            event_name=os.getenv("GITHUB_EVENT_NAME"),
        )
    except ModalReleaseConfigError as e:
        print(f"::error::{e}")
        return 1

    result = resolved.to_dict()
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
    if args.github_output:
        write_github_outputs(Path(args.github_output), result)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def resolve_release_from_event(
    event: dict[str, Any],
    *,
    fetch_pr_body_for_commit: Callable[[str, str], str | None],
    event_name: str | None = None,
) -> ResolvedModalRelease:
    if "pull_request" in event:
        return resolve_release_from_body(
            (event["pull_request"] or {}).get("body"),
            source="pull_request",
            deploy_when_missing=False,
        )

    if event_name == "workflow_dispatch":
        return ResolvedModalRelease(
            True,
            "workflow-dispatch-inputs",
            "release",
            workflow_dispatch_config_from_inputs(event.get("inputs") or {}),
        )

    if "head_commit" not in event:
        return ResolvedModalRelease(False, "unsupported-event", "none")

    message = (event.get("head_commit") or {}).get("message")
    if message != WEEKLY_UPDATE_COMMIT_MESSAGE:
        return ResolvedModalRelease(False, "push-not-release-commit", "none")

    repository = (event.get("repository") or {}).get("full_name")
    source_sha = event.get("before") or event.get("after")
    body = (
        fetch_pr_body_for_commit(repository, source_sha)
        if repository and source_sha
        else None
    )
    resolved = resolve_release_from_body(
        body,
        source="versioning-parent-pull-request",
        deploy_when_missing=False,
    )
    if resolved.should_deploy:
        return resolved

    return ResolvedModalRelease(
        True,
        "code-only",
        "code",
    )


def resolve_release_from_body(
    body: str | None,
    *,
    source: str,
    deploy_when_missing: bool,
) -> ResolvedModalRelease:
    if not body_contains_modal_release_config(body):
        deploy_mode = "code" if deploy_when_missing else "none"
        return ResolvedModalRelease(
            deploy_when_missing,
            f"{source}-missing",
            deploy_mode,
        )

    config = parse_modal_release_config_from_body(body)
    return ResolvedModalRelease(True, source, "release", config)


def workflow_dispatch_config_from_inputs(
    inputs: dict[str, Any],
) -> ModalReleaseConfig:
    default_config = release_config_to_dict(default_weekly_config())
    return ModalReleaseConfig.from_mapping(
        {
            "new_app_target": inputs.get(
                "new_app_target",
                default_config["new_app_target"],
            ),
            "promote_existing_frontier": _bool_input(
                inputs.get(
                    "promote_existing_frontier",
                    default_config["promote_existing_frontier"],
                )
            ),
            "cleanup_target": inputs.get(
                "cleanup_target",
                default_config["cleanup_target"],
            ),
        },
        allow_active_cleanup=True,
    )


def _bool_input(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ModalReleaseConfigError(
        "`promote_existing_frontier` must be true or false"
    )


def fetch_pr_body_for_commit(
    repository: str,
    sha: str,
) -> str | None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return None

    request = Request(
        f"https://api.github.com/repos/{repository}/commits/{sha}/pulls",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    with urlopen(request, timeout=30) as response:
        pull_requests = json.loads(response.read().decode("utf-8"))

    for pull_request in pull_requests:
        if pull_request.get("merged_at"):
            return pull_request.get("body")
    return pull_requests[0].get("body") if pull_requests else None


def write_github_outputs(
    output_path: Path,
    result: dict[str, Any],
) -> None:
    config = result.get("config") or {}
    outputs = {
        "should_deploy": str(result["should_deploy"]).lower(),
        "source": result["source"],
        "deploy_mode": result["deploy_mode"],
        "new_app_target": config.get("new_app_target", "none"),
        "promote_existing_frontier": str(
            config.get("promote_existing_frontier", False)
        ).lower(),
        "cleanup_target": config.get("cleanup_target", "none"),
        "config_json": json.dumps(config, sort_keys=True),
    }

    with output_path.open("a") as output_file:
        for key, value in outputs.items():
            output_file.write(f"{key}={value}\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve Modal release configuration for deployment."
    )
    parser.add_argument(
        "--event-path",
        default=os.getenv("GITHUB_EVENT_PATH"),
        required=os.getenv("GITHUB_EVENT_PATH") is None,
    )
    parser.add_argument("--output-json")
    parser.add_argument("--github-output", default=os.getenv("GITHUB_OUTPUT"))
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
