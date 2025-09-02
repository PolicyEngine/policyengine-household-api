import pytest
from unittest.mock import patch, MagicMock
import os

MOCK_PROMPT = "Test prompt for AI analysis"
MOCK_BUFFERED_RESPONSE = "Historical quote response"
MOCK_STREAMING_CHUNKS = ["Histo", "rical", " quot", "e res", "ponse"]


@pytest.fixture
def mock_config_ai_disabled():
    with patch(
        "policyengine_household_api.utils.computation_tree.get_config_value"
    ) as mock_config:

        def config_side_effect(key, default=None):
            if key == "ai.enabled":
                return False
            elif key == "ai.anthropic.api_key":
                return None
            return default

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def mock_config_ai_enabled_no_key():
    with patch(
        "policyengine_household_api.utils.computation_tree.get_config_value"
    ) as mock_config:

        def config_side_effect(key, default=None):
            if key == "ai.enabled":
                return True
            elif key == "ai.anthropic.api_key":
                return None
            return default

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def mock_config_ai_enabled_with_key():
    with patch(
        "policyengine_household_api.utils.computation_tree.get_config_value"
    ) as mock_config:

        def config_side_effect(key, default=None):
            if key == "ai.enabled":
                return True
            elif key == "ai.anthropic.api_key":
                return "test-api-key-123"
            return default

        mock_config.side_effect = config_side_effect
        yield mock_config


@pytest.fixture
def mock_anthropic_client():
    with patch(
        "policyengine_household_api.utils.computation_tree.anthropic.Anthropic"
    ) as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=MOCK_BUFFERED_RESPONSE)]
        mock_client.messages.create.return_value = mock_message

        mock_stream = MagicMock()
        mock_stream.text_stream = iter(MOCK_STREAMING_CHUNKS)
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=None)
        mock_client.messages.stream.return_value = mock_stream

        yield mock_anthropic


@pytest.fixture
def mock_env_no_anthropic_key(monkeypatch):
    if "ANTHROPIC_API_KEY" in os.environ:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    yield


@pytest.fixture
def mock_env_with_anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-env-api-key")
    yield
