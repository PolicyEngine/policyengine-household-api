from __future__ import annotations

import argparse

import modal

from policyengine_household_modal.worker_app import create_worker_app
from policyengine_household_modal.worker_deployment import (
    WorkerDeployment,
    WorkerResourceProfile,
    parse_package_versions_json,
)


def deploy_worker(deployment: WorkerDeployment) -> None:
    app = create_worker_app(deployment)
    with modal.enable_output():
        app.deploy(
            name=deployment.app_name,
            environment_name=deployment.modal_environment,
        )


def main() -> None:
    args = _parse_args()
    try:
        package_versions = parse_package_versions_json(
            args.package_versions_json
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    deploy_worker(
        WorkerDeployment(
            app_name=args.app_name,
            modal_environment=args.modal_environment,
            package_versions=package_versions,
            resource_profile=WorkerResourceProfile(args.resource_profile),
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy one configured household API Modal worker."
    )
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument("--package-versions-json", required=True)
    parser.add_argument(
        "--resource-profile",
        required=True,
        choices=[profile.value for profile in WorkerResourceProfile],
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
