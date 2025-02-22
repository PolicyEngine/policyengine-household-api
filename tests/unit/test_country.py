from tests.fixtures.country import (
  valid_household_requesting_ctc_calculation,
  country_package_name_us,
  country_id_us
)
from policyengine_household_api.country import PolicyEngineCountry
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
            enable_ai_explainer = False
        )

        # Then a tuple of a valid response and None is returned
        assert test_uuid_value == None
    
    def test_calculate_tree_requested(self):
        
        # Given a valid country calculation under current law with a tree requested
        country = PolicyEngineCountry(country_package_name_us, country_id_us)

        # When the calculate method is called
        untested_calculation_output, test_uuid_value = country.calculate(
            household=valid_household_requesting_ctc_calculation,
            reform=None,
            enable_ai_explainer = True
        )

        assert type(test_uuid_value) == str
        assert UUID(test_uuid_value).version == 4
