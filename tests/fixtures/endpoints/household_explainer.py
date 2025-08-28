import pytest
import json
from unittest.mock import patch

valid_household_requesting_calculation = {
    "people": {
        "you": {
            "age": {"2025": 40},
        },
        "your spouse": {"age": {"2025": 40}},
        "your first dependent": {"age": {"2025": 10}},
        "your second dependent": {"age": {"2025": 10}},
    },
    "tax_units": {
        "your tax_unit": {
            "members": [
                "you",
                "your spouse",
                "your first dependent",
                "your second dependent",
            ],
            "ctc": {"2025": None},
        },
    },
    "families": {
        "your family": {
            "members": [
                "you",
                "your spouse",
                "your first dependent",
                "your second dependent",
            ],
        }
    },
    "households": {
        "your household": {
            "members": [
                "you",
                "your spouse",
                "your first dependent",
                "your second dependent",
            ],
        }
    },
    "spm_units": {
        "your spm_unit": {
            "members": [
                "you",
                "your spouse",
                "your first dependent",
                "your second dependent",
            ],
        }
    },
    "marital_units": {
        "your marital unit": {"members": ["you", "your spouse"]},
        "your first dependent's marital unit": {
            "members": ["your first dependent"]
        },
        "your second dependent's marital unit": {
            "members": ["your second dependent"]
        },
    },
}

valid_entity_description = {
    "people": [
        "you",
        "your partner",
        "your first dependent" "your second dependent",
    ],
    "households": ["your household"],
    "spm_units": ["your household"],
    "families": ["your family"],
    "tax_units": ["your tax unit"],
    "marital_units": [
        "your marital unit",
        "your first dependent's marital unit",
        "your second dependent's marital unit",
    ],
}

valid_computation_tree_with_indiv_vars = [
    "  ctc<2025, (default)> = [4000.]",
    "    ctc_maximum_with_arpa_addition<2025, (default)> = [4000.]",
    "      ctc_maximum<2025, (default)> = [4000.]",
    "        ctc_individual_maximum<2025, (default)> = [   0.    0. 2000. 2000.]",
    "          ctc_child_individual_maximum<2025, (default)> = [   0.    0. 2000. 2000.]",
    "            age<2025, (default)> = [40. 40. 10. 10.]",
    "            is_tax_unit_dependent<2025, (default)> = [False False  True  True]",
    "              is_tax_unit_head<2025, (default)> = [ True False False False]",
    "                is_child<2025, (default)> = [False False  True  True]",
    "                  age<2025, (default)> = [40. 40. 10. 10.]",
    "                age<2025, (default)> = [40. 40. 10. 10.]",
    "              is_tax_unit_spouse<2025, (default)> = [False  True False False]",
    "                is_separated<2025, (default)> = [False False False False]",
    "                is_child<2025, (default)> = [False False  True  True]",
    "                is_tax_unit_head<2025, (default)> = [ True False False False]",
    "                age<2025, (default)> = [40. 40. 10. 10.]",
    "          ctc_adult_individual_maximum<2025, (default)> = [0. 0. 0. 0.]",
    "            is_tax_unit_dependent<2025, (default)> = [False False  True  True]",
    "            ctc_child_individual_maximum<2025, (default)> = [   0.    0. 2000. 2000.]",
]

valid_computation_tree_with_indiv_vars_uuid = (
    "123e4567-e89b-12d3-a456-426614174000"
)

# This object contains hypothetical household-level and
# individual-level variables to ensure we properly handle
# multiple entity types
valid_serialized_cloud_object_with_indiv_vars = {
    "uuid": valid_computation_tree_with_indiv_vars_uuid,
    "package_version": "1.160.0",
    "tree": valid_computation_tree_with_indiv_vars,
    "entity_description": valid_entity_description,
    "country_id": "us",
}

mock_claude_result_streaming = ["mock_claude", "_output_streaming"]

mock_claude_result_buffered = "mock_claude_output_buffered"

# A mock "container" containing all delineated "cloud objects"
mock_cloud_bucket = {}
mock_cloud_bucket[valid_computation_tree_with_indiv_vars_uuid] = (
    valid_serialized_cloud_object_with_indiv_vars
)

uuid_not_found = "uuid_not_found"


@pytest.fixture
def mock_streaming_output():
    with patch(
        "policyengine_household_api.endpoints.household_explainer.trigger_streaming_ai_analysis"
    ) as mock_streaming:

        def generate():
            for item in mock_claude_result_streaming:
                yield json.dumps({"response": item}) + "\n"

        # Accept any arguments (including the new api_key parameter)
        mock_streaming.side_effect = lambda prompt, api_key: generate()
        yield mock_streaming


@pytest.fixture
def mock_buffered_output():
    with patch(
        "policyengine_household_api.endpoints.household_explainer.trigger_buffered_ai_analysis"
    ) as mock_buffered:
        # Accept any arguments (including the new api_key parameter)
        mock_buffered.side_effect = lambda prompt, api_key: mock_claude_result_buffered
        yield mock_buffered


@pytest.fixture
def mock_cloud_download():
    def download_side_effect(*args, **kwargs):
        source_blob_name = kwargs.get("source_blob_name")
        if source_blob_name in mock_cloud_bucket:
            return json.dumps(mock_cloud_bucket[source_blob_name])
        elif source_blob_name == uuid_not_found:
            raise FileNotFoundError
        else:
            raise Exception

    with patch(
        "policyengine_household_api.utils.google_cloud.GoogleCloudStorageManager._download_json_from_cloud_storage"
    ) as mock_download:
        mock_download.side_effect = download_side_effect
        yield mock_download


@pytest.fixture(autouse=True)
def mock_anthropic_config_for_tests():
    """
    Automatically mock the Anthropic configuration check for all tests.
    This allows tests to run without requiring an actual Anthropic API key.
    """
    with patch("policyengine_household_api.endpoints.household_explainer._check_anthropic_configuration") as mock_check:
        # Make it return that Anthropic is configured with a test API key
        mock_check.return_value = (True, "sk-ant-test-key")
        yield mock_check
