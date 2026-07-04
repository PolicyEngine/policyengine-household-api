"""Deployment helpers shared by the Modal and Cloud Run worker images.

These live in the core package (not the modal-api project) because the Cloud
Run worker Dockerfile imports them without the modal SDK installed.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Mapping

COUNTRY_PACKAGE_DISTRIBUTIONS = {
    "uk": "policyengine_uk",
    "us": "policyengine_us",
}
PACKAGE_VERSIONS_ENV = "HOUSEHOLD_MODAL_PACKAGE_VERSIONS_JSON"


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


def snapshot_tax_benefit_systems() -> None:
    """Preload country tax-benefit systems into the worker image snapshot."""

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    country_package_names = (
        "policyengine_uk",
        "policyengine_us",
        "policyengine_canada",
        "policyengine_ng",
        "policyengine_il",
    )
    for package_name in country_package_names:
        logger.info("Pre-loading %s tax-benefit system...", package_name)
        country_package = importlib.import_module(package_name)
        country_package.CountryTaxBenefitSystem()

    logger.info("Household API tax-benefit systems pre-loaded")
