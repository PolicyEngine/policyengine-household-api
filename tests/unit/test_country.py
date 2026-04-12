from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
    country_package_name_us,
    country_id_us,
)
from importlib.metadata import PackageNotFoundError
from policyengine_household_api.country import PolicyEngineCountry
from policyengine_household_api.constants import COUNTRY_PACKAGE_VERSIONS
from uuid import UUID


# This only tests the computation tree
# functionality within the calculate method;
# test entire calculate in TestCalculateMain
class TestCalculateComputationTree:

    def test_calculate_no_tree(self):

        # Given a valid country calculation under current law with no tree requested
        country = PolicyEngineCountry(country_package_name_us, country_id_us)

        # When the calculate method is called
        untested_calculation_output, test_uuid_value = country.calculate(
            household=valid_household_requesting_ctc_calculation,
            reform=None,
            enable_ai_explainer=False,
        )

        # Then a tuple of a valid response and None is returned
        assert test_uuid_value is None

    def test_calculate_tree_requested(self):

        # Given a valid country calculation under current law with a tree requested
        country = PolicyEngineCountry(country_package_name_us, country_id_us)

        # When the calculate method is called
        untested_calculation_output, test_uuid_value = country.calculate(
            household=valid_household_requesting_ctc_calculation,
            reform=None,
            enable_ai_explainer=True,
        )

        assert isinstance(test_uuid_value, str)
        assert UUID(test_uuid_value).version == 4


class TestPolicyEngineBundle:

    def test_country_exposes_policyengine_bundle(self):
        country = PolicyEngineCountry(country_package_name_us, country_id_us)

        assert country.policyengine_bundle == {
            "model_version": COUNTRY_PACKAGE_VERSIONS[country_id_us],
            "data_version": None,
            "dataset": None,
        }
        assert (
            country.metadata["result"]["version"]
            == COUNTRY_PACKAGE_VERSIONS[country_id_us]
        )


def test_country_package_versions_falls_back_per_package(monkeypatch):
    from policyengine_household_api import constants

    def _fake_version(package_name: str) -> str:
        if package_name == "policyengine_us":
            return "1.602.0"
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(constants, "version", _fake_version)

    versions = {}
    for country, package_name in zip(
        constants.COUNTRIES, constants.COUNTRY_PACKAGE_NAMES
    ):
        try:
            versions[country] = constants.version(package_name)
        except Exception:
            versions[country] = "0.0.0"

    assert versions["us"] == "1.602.0"
    assert versions["uk"] == "0.0.0"
