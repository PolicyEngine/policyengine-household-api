from __future__ import annotations

import modal
import os

from policyengine_household_api.modal_release._image_setup import (
    snapshot_tax_benefit_systems,
)


def household_api_worker_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.12")
        .uv_sync(".", frozen=True)
        .add_local_python_source("policyengine_household_api", copy=True)
        .add_local_dir("config", remote_path="/app/config", copy=True)
        .run_function(snapshot_tax_benefit_systems)
    )


def household_api_gateway_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install(
            "flask>=2.2",
            "modal>=1.3.0",
            "pyyaml>=6",
        )
        .add_local_python_source("policyengine_household_api", copy=True)
    )


def household_api_secret() -> modal.Secret:
    return modal.Secret.from_name(
        os.getenv("HOUSEHOLD_MODAL_SECRET_NAME", "household-api")
    )
