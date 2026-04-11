from tests.fixtures.country import (
    valid_household_requesting_ctc_calculation,
    country_package_name_us,
    country_id_us,
)
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
