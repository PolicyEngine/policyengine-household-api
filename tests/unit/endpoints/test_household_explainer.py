from policyengine_household_api.utils.config_loader import get_config_value
from tests.fixtures.endpoints.household_explainer import (
    valid_entity_description,
    valid_computation_tree_with_indiv_vars,
    valid_serialized_cloud_object_with_indiv_vars,
    valid_computation_tree_with_indiv_vars_uuid,
    valid_household_requesting_calculation,
    mock_buffered_output,
    mock_streaming_output,
    mock_cloud_download,
    mock_claude_result_buffered,
    mock_claude_result_streaming,
    uuid_not_found,
)
import json
from typing import Generator
from copy import deepcopy


class TestGenerateAIExplainer:
    # Mock record fetched from storage
    # Mock Claude

    auth_headers = {
        "Authorization": f"Bearer {get_config_value('auth.auth0.test_token')}",
    }

    # Test valid UUID
    def test_valid_uuid(
        self,
        client,
        mock_buffered_output,
        mock_cloud_download,
    ):
        request_with_valid_uuid = {
            "computation_tree_uuid": valid_computation_tree_with_indiv_vars_uuid,
            "household": valid_household_requesting_calculation,
            "use_streaming": False,
        }

        response = client.post(
            "/us/ai-analysis",
            json=request_with_valid_uuid,
            headers=self.auth_headers,
        )

        assert response.status_code == 200

        response_json = json.loads(response.data)
        assert response_json["response"] == mock_claude_result_buffered

    def test_uuid_not_found(
        self,
        client,
        mock_buffered_output,
        mock_cloud_download,
    ):

        request_with_invalid_uuid = {
            "computation_tree_uuid": uuid_not_found,
            "household": valid_household_requesting_calculation,
            "use_streaming": False,
        }

        response = client.post(
            "/us/ai-analysis",
            json=request_with_invalid_uuid,
            headers=self.auth_headers,
        )

        assert response.status_code == 400

        response_json = json.loads(response.data)
        assert (
            response_json["message"]
            == f"Unable to find record with UUID {uuid_not_found}"
        )

    # Test UUID invalid - wrong type
    def test_invalid_uuid_incorrect_type(
        self,
        client,
        mock_buffered_output,
        mock_cloud_download,
    ):
        request_with_invalid_uuid = {
            "computation_tree_uuid": "invalid_uuid",
            "household": valid_household_requesting_calculation,
            "use_streaming": False,
        }

        response = client.post(
            "/us/ai-analysis",
            json=request_with_invalid_uuid,
            headers=self.auth_headers,
        )

        assert response.status_code == 500

        response_json = json.loads(response.data)
        assert (
            "Error generating tracer analysis result using Claude: "
            in response_json["message"]
        )

    # Test valid household, streaming
    def test_valid_household_with_streaming(
        self,
        client,
        mock_streaming_output,
        mock_cloud_download,
    ):
        request_with_streaming_output = {
            "computation_tree_uuid": valid_computation_tree_with_indiv_vars_uuid,
            "household": valid_household_requesting_calculation,
            "use_streaming": True,
        }

        response = client.post(
            "/us/ai-analysis",
            json=request_with_streaming_output,
            headers=self.auth_headers,
        )

        assert response.status_code == 200

        response_bytes: bytes = response.data
        response_str = response_bytes.decode("utf-8")

        json_objects = []
        for line in response_str.strip().split("\n"):
            if line:
                json_objects.append(json.loads(line))

        results = [obj["response"] for obj in json_objects]
        assert results == mock_claude_result_streaming

    # Test invalid household, too many variables are requesting computation
    def test_invalid_household_too_many_variables(
        self,
        client,
        mock_buffered_output,
        mock_cloud_download,
    ):
        extra_variable = {"ctc_individual_maximum": {"2025": None}}

        invalid_household = deepcopy(valid_household_requesting_calculation)

        # Add another variable for computation
        invalid_household["people"]["you"].update(extra_variable)

        request_with_invalid_household = {
            "computation_tree_uuid": valid_computation_tree_with_indiv_vars_uuid,
            "household": invalid_household,
            "use_streaming": False,
        }

        response = client.post(
            "/us/ai-analysis",
            json=request_with_invalid_household,
            headers=self.auth_headers,
        )

        assert response.status_code == 500

        response_json = json.loads(response.data)
        assert (
            "More than 1 variable(s) was/were provided:"
            in response_json["message"]
        )

    # Test invalid household, no variables requesting computation
    def test_invalid_household_no_nones(
        self,
        client,
        mock_buffered_output,
        mock_cloud_download,
    ):
        invalid_household = deepcopy(valid_household_requesting_calculation)

        # Overwrite all variables requesting computation with finalized value
        invalid_household["tax_units"]["your tax_unit"]["ctc"]["2025"] = 2000

        request_with_invalid_household = {
            "computation_tree_uuid": valid_computation_tree_with_indiv_vars_uuid,
            "household": invalid_household,
            "use_streaming": False,
        }

        response = client.post(
            "/us/ai-analysis",
            json=request_with_invalid_household,
            headers=self.auth_headers,
        )

        assert response.status_code == 400

        response_json = json.loads(response.data)
        assert (
            "Household must include at least one variable set to null"
            in response_json["message"]
        )
