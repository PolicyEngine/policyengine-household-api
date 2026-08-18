from __future__ import annotations

import os

import modal

# Read docs/engineering/skills/modal-images.md before changing this module.
#
# The locked third-party requirements for these images are exported from the
# workspace lockfile by .github/scripts/modal-deploy-release.sh before any
# `modal deploy` runs (Modal's Image.uv_sync does not support uv workspaces).
# Keep these factories free of eager work: this module is re-imported inside
# running containers, where no repository checkout exists.
WORKER_REQUIREMENTS_FILE = "requirements-modal-worker.txt"

FIRST_PARTY_PACKAGES = (
    "policyengine_household_api",
    "policyengine_household_common",
    "policyengine_household_analytics",
    "policyengine_household_modal",
)


def household_api_worker_image() -> modal.Image:
    if not modal.is_local():
        # Inside a running container this module is re-imported for the app
        # definitions, but the image is already built; return a placeholder
        # instead of re-running the deploy-machine-only build steps below.
        return modal.Image.debian_slim(python_version="3.13")

    # Imported lazily: this module is also imported inside canary containers,
    # whose image deliberately does not ship the core package.
    from policyengine_household_api.deployment import (
        country_package_install_specs,
        preload_country_packages,
    )

    image = modal.Image.debian_slim(python_version="3.13").uv_pip_install(
        requirements=[WORKER_REQUIREMENTS_FILE]
    )
    package_specs = country_package_install_specs()
    if package_specs:
        image = image.uv_pip_install(*package_specs)
    return (
        image.add_local_python_source(*FIRST_PARTY_PACKAGES, copy=True)
        .add_local_dir("config", remote_path="/app/config", copy=True)
        .run_function(preload_country_packages)
    )


def household_api_canary_image() -> modal.Image:
    return modal.Image.debian_slim(python_version="3.13")


def household_api_secret() -> modal.Secret:
    return modal.Secret.from_name(
        os.getenv("HOUSEHOLD_MODAL_SECRET_NAME", "household-api")
    )
