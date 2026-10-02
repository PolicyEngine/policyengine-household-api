from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from policyengine_household_modal.worker_deployment import (
    WorkerDeployment,
    WorkerResourceProfile,
    parse_package_versions_json,
)
from policyengine_household_common.release_config import (
    ModalReleaseConfig,
    NewAppTarget,
)


def build_worker_deployment_plan(
    active_deployments: list[Mapping[str, Any]],
    *,
    deploy_mode: str,
    modal_environment: str,
    config: ModalReleaseConfig | None = None,
    new_app_name: str | None = None,
    new_package_versions: Mapping[str, str] | None = None,
) -> list[WorkerDeployment]:
    active = [
        _deployment_from_mapping(
            deployment,
            modal_environment=modal_environment,
        )
        for deployment in active_deployments
    ]

    if deploy_mode == "code":
        return _consolidate_deployments(active)
    if deploy_mode != "release":
        raise ValueError(f"Unsupported Modal deploy mode: {deploy_mode}")
    if config is None:
        raise ValueError("Release mode requires Modal release configuration")

    requested: list[WorkerDeployment] = []
    if config.promote_existing_frontier:
        requested.extend(
            WorkerDeployment(
                app_name=deployment.app_name,
                modal_environment=modal_environment,
                package_versions=deployment.package_versions,
                resource_profile=WorkerResourceProfile.CURRENT,
            )
            for deployment in active
            if deployment.resource_profile == WorkerResourceProfile.FRONTIER
        )

    if config.deploys_new_app:
        if not new_app_name:
            raise ValueError("A new worker app name is required")
        if new_package_versions is None:
            raise ValueError("New worker package versions are required")

        new_profile = (
            WorkerResourceProfile.CURRENT
            if config.new_app_target
            in {NewAppTarget.CURRENT, NewAppTarget.BOTH}
            else WorkerResourceProfile.FRONTIER
        )
        if any(
            deployment.app_name == new_app_name
            and deployment.resource_profile == WorkerResourceProfile.CURRENT
            for deployment in active
        ):
            # Do not reduce an app that still serves current traffic before
            # the manifest update completes, even if its final target is only
            # frontier.
            new_profile = WorkerResourceProfile.CURRENT

        requested.append(
            WorkerDeployment(
                app_name=new_app_name,
                modal_environment=modal_environment,
                package_versions=new_package_versions,
                resource_profile=new_profile,
            )
        )

    return _consolidate_deployments(requested)


def _consolidate_deployments(
    deployments: list[WorkerDeployment],
) -> list[WorkerDeployment]:
    consolidated: list[WorkerDeployment] = []
    index_by_name: dict[str, int] = {}

    for deployment in deployments:
        existing_index = index_by_name.get(deployment.app_name)
        if existing_index is None:
            index_by_name[deployment.app_name] = len(consolidated)
            consolidated.append(deployment)
            continue

        existing = consolidated[existing_index]
        if dict(existing.package_versions) != dict(
            deployment.package_versions
        ):
            raise ValueError(
                f"Modal worker app `{deployment.app_name}` cannot be "
                "deployed with conflicting package versions"
            )
        if (
            deployment.resource_profile == WorkerResourceProfile.CURRENT
            and existing.resource_profile != WorkerResourceProfile.CURRENT
        ):
            consolidated[existing_index] = deployment

    return consolidated


def _deployment_from_mapping(
    deployment: Mapping[str, Any],
    *,
    modal_environment: str,
) -> WorkerDeployment:
    try:
        app_name = deployment["app_name"]
        package_versions = deployment["package_versions"]
        resource_profile = deployment["resource_profile"]
    except KeyError as exc:
        raise ValueError(
            f"Active worker deployment is missing `{exc.args[0]}`"
        ) from exc
    if not isinstance(app_name, str):
        raise ValueError("Active worker app name must be a string")
    if not isinstance(package_versions, Mapping):
        raise ValueError("Active worker package versions must be a mapping")

    return WorkerDeployment(
        app_name=app_name,
        modal_environment=modal_environment,
        package_versions=package_versions,
        resource_profile=WorkerResourceProfile(resource_profile),
    )


def main() -> None:
    args = _parse_args()
    active_deployments = json.loads(
        Path(args.active_deployments_json).read_text()
    )
    if not isinstance(active_deployments, list):
        raise SystemExit("Active worker deployments must be a JSON list")

    config = None
    if args.deploy_mode == "release":
        config = ModalReleaseConfig.from_mapping(
            json.loads(args.config_json),
            allow_active_cleanup=True,
        )

    try:
        plan = build_worker_deployment_plan(
            active_deployments,
            deploy_mode=args.deploy_mode,
            modal_environment=args.modal_environment,
            config=config,
            new_app_name=args.new_app_name,
            new_package_versions=parse_package_versions_json(
                args.new_package_versions_json
            ),
        )
    except (TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    lines = [
        "\t".join(
            (
                deployment.app_name,
                json.dumps(
                    dict(deployment.package_versions),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                deployment.resource_profile.value,
            )
        )
        for deployment in plan
    ]
    Path(args.output_tsv).write_text("\n".join(lines) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan typed Modal worker deployments for a release."
    )
    parser.add_argument("--active-deployments-json", required=True)
    parser.add_argument(
        "--deploy-mode", required=True, choices=("code", "release")
    )
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument("--config-json", default="{}")
    parser.add_argument("--new-app-name")
    parser.add_argument("--new-package-versions-json", default="{}")
    parser.add_argument("--output-tsv", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
