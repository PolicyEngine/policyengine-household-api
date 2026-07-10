"""Deployment helpers shared by the Modal and Cloud Run worker images.

These live in the core package (not the modal-api project) because the Cloud
Run worker Dockerfile imports them without the modal SDK installed.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
from datetime import date
from typing import Any, Mapping, Sequence

COUNTRY_PACKAGE_DISTRIBUTIONS = {
    "uk": "policyengine_uk",
    "us": "policyengine_us",
}
PACKAGE_VERSIONS_ENV = "HOUSEHOLD_MODAL_PACKAGE_VERSIONS_JSON"

# Parameter values resolve through per-instant projections that
# policyengine-core builds lazily: the first request to touch a
# never-seen instant pays an eagerly recursive build of the full
# parameter tree at that instant (~126k nodes for the US system), and a
# heavy household touches ~20 distinct instants via monthly periods and
# fiscal-year lookbacks. Pre-building a window wide enough for any
# plausible request start plus its lookbacks keeps that cost out of the
# request path (issue #1624).
PREWARM_YEARS_BACK = 3
PREWARM_YEARS_FORWARD = 2


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


def parameter_prewarm_instants(today: date | None = None) -> list[str]:
    """Monthly instants covering every date a request can plausibly touch."""
    if today is None:
        today = date.today()
    return [
        f"{year}-{month:02d}-01"
        for year in range(
            today.year - PREWARM_YEARS_BACK,
            today.year + PREWARM_YEARS_FORWARD + 1,
        )
        for month in range(1, 13)
    ]


def prewarm_parameter_caches(
    tax_benefit_systems: Mapping[str, Any] | None = None,
    instants: Sequence[str] | None = None,
) -> None:
    """Eagerly build parameter at-instant projections on the runtime systems.

    Must run against the tax-benefit system instances that serve
    requests (the caches live on the instances): defaults to the
    ``COUNTRIES`` singletons. Called from the Modal worker's
    memory-snapshot hook so the populated caches ride the snapshot and
    restored containers serve their first heavy request warm instead of
    paying a 60-105s build against the failover gateway's 90s budget
    (issue #1624).
    """
    logger = logging.getLogger(__name__)

    if tax_benefit_systems is None:
        from policyengine_household_api.country import COUNTRIES

        tax_benefit_systems = {
            country_id: country.tax_benefit_system
            for country_id, country in COUNTRIES.items()
        }
    if instants is None:
        instants = parameter_prewarm_instants()

    for country_id, system in tax_benefit_systems.items():
        started_at = time.monotonic()
        for instant in instants:
            system.get_parameters_at_instant(instant)
        logger.info(
            "Pre-built %d parameter instants for %s in %.1fs",
            len(instants),
            country_id,
            time.monotonic() - started_at,
        )


def preload_country_packages() -> None:
    """Import and build the country packages during the image build.

    Runs via ``Image.run_function``, which snapshots the resulting
    FILESYSTEM as an image layer -- only disk side effects persist
    (compiled bytecode, data files downloaded at import/build). The
    in-memory system instances built here are discarded; memory-state
    warming belongs in the worker's ``@modal.enter(snap=True)`` hook
    (see ``prewarm_parameter_caches``).
    """

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
