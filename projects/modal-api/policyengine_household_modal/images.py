from __future__ import annotations

import os
import subprocess
import tempfile

import modal

FIRST_PARTY_PACKAGES = (
    "policyengine_household_api",
    "policyengine_household_common",
    "policyengine_household_analytics",
    "policyengine_household_modal",
)


def _locked_requirements_file(*, worker_extra: bool) -> str:
    """Export the member's locked third-party requirements to a temp file.

    Modal's ``Image.uv_sync`` does not support uv workspaces, so the deploy
    machine (a full ``uv sync --all-packages`` checkout) exports the locked
    closure instead; first-party members are excluded and added to the image
    as local Python sources below.
    """
    command = [
        "uv",
        "export",
        "--frozen",
        "--no-dev",
        "--no-emit-workspace",
        "--no-hashes",
        "--package",
        "policyengine-household-modal-api",
    ]
    if worker_extra:
        command += ["--extra", "worker"]
    requirements = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="household-modal-requirements-",
        delete=False,
    )
    with requirements:
        subprocess.run(
            command,
            check=True,
            stdout=requirements,
            text=True,
        )
    return requirements.name


def household_api_worker_image() -> modal.Image:
    # Imported lazily: this module is also imported inside gateway and canary
    # containers, whose images deliberately do not ship the core package.
    from policyengine_household_api.deployment import (
        country_package_install_specs,
        snapshot_tax_benefit_systems,
    )

    image = modal.Image.debian_slim(python_version="3.13").uv_pip_install(
        requirements=[_locked_requirements_file(worker_extra=True)]
    )
    package_specs = country_package_install_specs()
    if package_specs:
        image = image.uv_pip_install(*package_specs)
    return (
        image.add_local_python_source(*FIRST_PARTY_PACKAGES, copy=True)
        .add_local_dir("config", remote_path="/app/config", copy=True)
        .run_function(snapshot_tax_benefit_systems)
    )


def household_api_gateway_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.13")
        .uv_pip_install(
            requirements=[_locked_requirements_file(worker_extra=False)]
        )
        .add_local_python_source(
            "policyengine_household_common",
            "policyengine_household_modal",
            copy=True,
        )
    )


def household_api_canary_image() -> modal.Image:
    return modal.Image.debian_slim(python_version="3.13")


def household_api_secret() -> modal.Secret:
    return modal.Secret.from_name(
        os.getenv("HOUSEHOLD_MODAL_SECRET_NAME", "household-api")
    )
