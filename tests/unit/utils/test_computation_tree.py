import pytest
import json
from unittest.mock import patch, MagicMock
from policyengine_household_api.utils.computation_tree import (
    trigger_streaming_ai_analysis,
    trigger_buffered_ai_analysis,
)
from tests.fixtures.utils.computation_tree import (
    MOCK_PROMPT,
    MOCK_BUFFERED_RESPONSE,
    MOCK_STREAMING_CHUNKS,
    mock_config_ai_disabled,
    mock_config_ai_enabled_no_key,
    mock_config_ai_enabled_with_key,
    mock_anthropic_client,
    mock_env_no_anthropic_key,
    mock_env_with_anthropic_key,
)


class TestTriggerStreamingAIAnalysis:

    def test__given_ai_disabled__then_returns_none(
        self, mock_config_ai_disabled
    ):
        result = trigger_streaming_ai_analysis(MOCK_PROMPT)

        assert result is None
        mock_config_ai_disabled.assert_any_call("ai.enabled")

    def test__given_ai_enabled_but_no_api_key__then_raises_error(
        self, mock_config_ai_enabled_no_key
    ):
        with pytest.raises(Exception) as exc_info:
            result = trigger_streaming_ai_analysis(MOCK_PROMPT)
            # The error occurs when trying to consume the generator
            if result is not None:
                list(result)

        assert "api_key" in str(exc_info.value).lower() or "API" in str(
            exc_info.value
        )
        mock_config_ai_enabled_no_key.assert_any_call("ai.enabled")
        mock_config_ai_enabled_no_key.assert_any_call("ai.anthropic.api_key")

    def test__given_ai_enabled_with_api_key__then_returns_generator(
        self, mock_config_ai_enabled_with_key, mock_anthropic_client
    ):
        result = trigger_streaming_ai_analysis(MOCK_PROMPT)

        assert result is not None

        chunks = list(result)

        expected_chunks = [
            json.dumps({"response": chunk}) + "\n"
            for chunk in MOCK_STREAMING_CHUNKS
        ]
        assert chunks == expected_chunks

        mock_config_ai_enabled_with_key.assert_any_call("ai.enabled")
        mock_config_ai_enabled_with_key.assert_any_call("ai.anthropic.api_key")
        mock_anthropic_client.assert_called_once_with(
            api_key="test-api-key-123"
        )


class TestTriggerBufferedAIAnalysis:

    def test__given_ai_disabled__then_returns_none(
        self, mock_config_ai_disabled
    ):
        result = trigger_buffered_ai_analysis(MOCK_PROMPT)

        assert result is None
        mock_config_ai_disabled.assert_any_call("ai.enabled")

    def test__given_ai_enabled_but_no_api_key__then_raises_error(
        self, mock_config_ai_enabled_no_key
    ):
        with pytest.raises(Exception) as exc_info:
            trigger_buffered_ai_analysis(MOCK_PROMPT)

        assert "api_key" in str(exc_info.value).lower() or "API" in str(
            exc_info.value
        )
        mock_config_ai_enabled_no_key.assert_any_call("ai.enabled")
        mock_config_ai_enabled_no_key.assert_any_call("ai.anthropic.api_key")

    def test__given_ai_enabled_with_api_key__then_returns_response(
        self, mock_config_ai_enabled_with_key, mock_anthropic_client
    ):
        result = trigger_buffered_ai_analysis(MOCK_PROMPT)

        assert result == MOCK_BUFFERED_RESPONSE

        mock_config_ai_enabled_with_key.assert_any_call("ai.enabled")
        mock_config_ai_enabled_with_key.assert_any_call("ai.anthropic.api_key")
        mock_anthropic_client.assert_called_once_with(
            api_key="test-api-key-123"
        )
