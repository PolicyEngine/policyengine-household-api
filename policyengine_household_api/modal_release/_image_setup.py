from __future__ import annotations

import importlib
import logging


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
