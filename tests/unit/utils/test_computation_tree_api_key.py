"""
Tests for the API key parameter in computation_tree AI functions.
"""

import pytest
from policyengine_household_api.utils.computation_tree import (
    trigger_streaming_ai_analysis,
    trigger_buffered_ai_analysis,
)
from tests.fixtures.utils.computation_tree_api_key import (
    mock_anthropic_client,
    mock_parse_claude_message,
)


class TestComputationTreeAPIKey:
    """Test that computation_tree functions require API key parameter."""
    
    def test__given_no_api_key__raises_error(self):
        """Test that streaming analysis raises ValueError without API key."""
        with pytest.raises(ValueError, match="Anthropic API key is required"):
            # Call without API key (empty string)
            gen = trigger_streaming_ai_analysis("test prompt", "")
            # Try to consume the generator
            list(gen)
    
    def test__given_none_api_key__streaming_analysis_raises_error(self):
        """Test that streaming analysis raises ValueError with None API key."""
        with pytest.raises(ValueError, match="Anthropic API key is required"):
            # Call with None API key
            gen = trigger_streaming_ai_analysis("test prompt", None)
            list(gen)
    
    def test__given_no_api_key__buffered_analysis_raises_error(self):
        """Test that buffered analysis raises ValueError without API key."""
        with pytest.raises(ValueError, match="Anthropic API key is required"):
            trigger_buffered_ai_analysis("test prompt", "")
    
    def test__given_none_api_key__buffered_analysis_raises_error(self):
        """Test that buffered analysis raises ValueError with None API key."""
        with pytest.raises(ValueError, match="Anthropic API key is required"):
            trigger_buffered_ai_analysis("test prompt", None)
    
    def test__given_api_key__triggers_streaming_analysis(self, mock_anthropic_client):
        """Test that streaming analysis uses the provided API key."""
        mock_anthropic_class, mock_client = mock_anthropic_client
        
        # Call the function with a valid API key
        gen = trigger_streaming_ai_analysis("test prompt", "sk-ant-test-key")
        # Consume the generator to trigger the API call
        list(gen())
        
        # Verify Anthropic client was created with the provided key
        mock_anthropic_class.assert_called_once_with(api_key="sk-ant-test-key")
    
    def test__given_api_key__triggers_buffered_analysis(self, mock_anthropic_client, mock_parse_claude_message):
        """Test that buffered analysis uses the provided API key."""
        mock_anthropic_class, mock_client = mock_anthropic_client
        
        # Call the function with a valid API key
        result = trigger_buffered_ai_analysis("test prompt", "sk-ant-test-key")
        
        # Verify Anthropic client was created with the provided key
        mock_anthropic_class.assert_called_once_with(api_key="sk-ant-test-key")
        
        # Verify response
        assert result == "test response"