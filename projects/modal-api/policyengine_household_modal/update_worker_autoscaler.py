from __future__ import annotations

import argparse

import modal

from policyengine_household_modal.worker_resources import (
    PRODUCTION_WORKER_RESOURCE_OPTIONS,
)


def update_worker_autoscaler(
    *,
    app_name: str,
    modal_environment: str,
    resource_profile: str,
) -> None:
    worker_class = modal.Cls.from_name(
        app_name,
        "HouseholdWorker",
        environment_name=modal_environment,
    )
    requested = PRODUCTION_WORKER_RESOURCE_OPTIONS[resource_profile]
    worker_class().update_autoscaler(**requested)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update a deployed household worker's autoscaler."
    )
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--modal-environment", required=True)
    parser.add_argument(
        "--resource-profile",
        required=True,
        choices=PRODUCTION_WORKER_RESOURCE_OPTIONS,
    )
    args = parser.parse_args()
    update_worker_autoscaler(
        app_name=args.app_name,
        modal_environment=args.modal_environment,
        resource_profile=args.resource_profile,
    )


if __name__ == "__main__":
    main()
