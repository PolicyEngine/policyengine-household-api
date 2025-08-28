"""
Fixtures for testing API key parameter in computation_tree functions.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing API key usage."""
    with patch(
        "policyengine_household_api.utils.computation_tree.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        # Setup for streaming analysis
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=None)
        mock_stream.text_stream = []
        mock_client.messages.stream.return_value = mock_stream

        # Setup for buffered analysis
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test response")]
        mock_client.messages.create.return_value = mock_response

        yield mock_anthropic_class, mock_client


@pytest.fixture
def mock_parse_claude_message():
    """Mock parse_string_from_claude_message function."""
    with patch(
        "policyengine_household_api.utils.computation_tree.parse_string_from_claude_message"
    ) as mock_parse:
        mock_parse.return_value = "test response"
        yield mock_parse
