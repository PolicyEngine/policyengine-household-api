"""
Tests for Anthropic API key configuration in the household_explainer endpoint.
"""

import pytest
import json
from policyengine_household_api.endpoints.household_explainer import (
    generate_ai_explainer,
    _check_anthropic_configuration,
    _create_unauthorized_response,
)
from tests.fixtures.endpoints.household_explainer_auth import (
    mock_ai_disabled_no_key,
    mock_ai_enabled_with_key,
    mock_ai_enabled_no_key,
    mock_backward_compatibility_env_key,
    mock_flask_app,
    mock_household_model_us,
    mock_flatten_variables_empty,
    mock_flatten_variables_with_data,
    mock_google_cloud_storage_not_found,
    test_household_payload,
    test_household_payload_with_null,
)


class TestAnthropicConfiguration:
    """Test Anthropic configuration checking helper functions."""
    
    def test__given_ai_disabled_and_no_api_key__returns_401(self, mock_flask_app, mock_ai_disabled_no_key, test_household_payload):
        """Test that endpoint returns 401 when AI is disabled and no API key is present."""
        with mock_flask_app.test_request_context(json=test_household_payload):
            # Call the endpoint
            response = generate_ai_explainer("us")

            # Assert 401 response
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data["status"] == "error"
            assert "Anthropic API key is not configured" in data["message"]
        """Test that configuration check returns False when AI is disabled and no key present."""
        # Call the function
        is_configured, api_key = _check_anthropic_configuration()
        
        # Assert results
        assert is_configured is False
        assert api_key is None
    
    def test__given_api_key__returns_true(self, mock_ai_enabled_with_key):
        """Test that configuration check returns True when AI is enabled with API key."""
        # Call the function
        is_configured, api_key = _check_anthropic_configuration()
        
        # Assert results
        assert is_configured is True
        assert api_key == "sk-ant-config-key"
    
    def test__given_backward_compatible_env_var__returns_true(self, mock_backward_compatibility_env_key):
        """Test backward compatibility with environment variable."""
        # Call the function
        is_configured, api_key = _check_anthropic_configuration()
        
        # Assert results
        assert is_configured is True
        assert api_key == "sk-ant-env-key"
    
class TestHouseholdExplainerAuth:
    """Test Anthropic API key checking in household_explainer endpoint."""
    
    def test__given_ai_disabled_and_no_api_key__returns_401(self, mock_flask_app, mock_ai_disabled_no_key, test_household_payload):
        """Test that endpoint returns 401 when AI is disabled and no API key is present."""
        with mock_flask_app.test_request_context(json=test_household_payload):
            # Call the endpoint
            response = generate_ai_explainer("us")
            
            # Assert 401 response
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data["status"] == "error"
            assert "Anthropic API key is not configured" in data["message"]
    
    def test__given_ai_enabled_but_no_api_key__returns_401(self, mock_flask_app, mock_ai_enabled_no_key, test_household_payload):
        """Test that endpoint returns 401 when AI is enabled but no API key is provided."""
        with mock_flask_app.test_request_context(json=test_household_payload):
            # Call the endpoint
            response = generate_ai_explainer("us")
            
            # Assert 401 response
            assert response.status_code == 401
            data = json.loads(response.data)
            assert data["status"] == "error"
            assert "Anthropic API key is not configured" in data["message"]
    
    def test__given_api_key_in_env_var__auto_enables_ai(self, mock_flask_app, mock_backward_compatibility_env_key, 
                                                         mock_household_model_us, mock_flatten_variables_empty,
                                                         test_household_payload):
        """Test backward compatibility: API key in env var auto-enables AI."""
        with mock_flask_app.test_request_context(json=test_household_payload):
            # Call the endpoint
            response = generate_ai_explainer("us")
            
            # Should proceed past auth check (fail at variable validation)
            assert response.status_code == 400  # Bad request due to no null variables
            data = json.loads(response.data)
            assert "at least one variable set to null" in data["message"]
    
    def test__given_ai_enabled_with_api_key__proceeds_with_request(self, mock_flask_app, mock_ai_enabled_with_key,
                                                                   mock_household_model_us, mock_flatten_variables_empty,
                                                                   test_household_payload):
        """Test that endpoint proceeds when AI is enabled and API key is configured."""
        with mock_flask_app.test_request_context(json=test_household_payload):
            # Call the endpoint
            response = generate_ai_explainer("us")
            
            # Should proceed past auth check (fail at variable validation)
            assert response.status_code == 400  # Bad request due to no null variables
            data = json.loads(response.data)
            assert "at least one variable set to null" in data["message"]