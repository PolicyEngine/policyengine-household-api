from __future__ import annotations

import json
import modal
import os
from typing import Mapping

from policyengine_household_api.modal_release._image_setup import (
    snapshot_tax_benefit_systems,
)


COUNTRY_PACKAGE_DISTRIBUTIONS = {
    "uk": "policyengine_uk",
    "us": "policyengine_us",
}
PACKAGE_VERSIONS_ENV = "HOUSEHOLD_MODAL_PACKAGE_VERSIONS_JSON"


def household_api_worker_image() -> modal.Image:
    image = modal.Image.debian_slim(python_version="3.13").uv_sync(
        ".", frozen=True
    )
    package_specs = country_package_install_specs()
    if package_specs:
        image = image.uv_pip_install(*package_specs)
    return (
        image.add_local_python_source(
            "policyengine_household_api",
            "policyengine_household_common",
            copy=True,
        )
        .add_local_dir("config", remote_path="/app/config", copy=True)
        .run_function(snapshot_tax_benefit_systems)
    )


def household_api_gateway_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.13")
        .pip_install(
            "flask>=2.2",
            "modal>=1.3.0",
            "policyengine-observability[flask]>=1.0.0",
            "pyyaml>=6",
        )
        .add_local_python_source(
            "policyengine_household_api",
            "policyengine_household_common",
            copy=True,
        )
    )


def household_api_canary_image() -> modal.Image:
    return modal.Image.debian_slim(python_version="3.13")


def household_api_secret() -> modal.Secret:
    return modal.Secret.from_name(
        os.getenv("HOUSEHOLD_MODAL_SECRET_NAME", "household-api")
    )


def country_package_install_specs(
    package_versions: Mapping[str, str] | None = None,
) -> list[str]:
    versions = (
        dict(package_versions)
        if package_versions is not None
        else deployment_package_versions_from_env()
    )
    return [
        f"{COUNTRY_PACKAGE_DISTRIBUTIONS[country]}=={versions[country]}"
        for country in sorted(COUNTRY_PACKAGE_DISTRIBUTIONS)
        if versions.get(country)
    ]


def deployment_package_versions_from_env() -> dict[str, str]:
    raw_value = os.getenv(PACKAGE_VERSIONS_ENV)
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"{PACKAGE_VERSIONS_ENV} must contain JSON object data"
        ) from e
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{PACKAGE_VERSIONS_ENV} must be a JSON object")
    return {
        country: version
        for country, version in parsed.items()
        if country in COUNTRY_PACKAGE_DISTRIBUTIONS
        and isinstance(version, str)
        and version
    }
