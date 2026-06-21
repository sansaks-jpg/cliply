import pytest
from unittest.mock import patch, MagicMock

from app.engine.llm import call_openai_llm

@patch("app.engine.llm.OPENAI_API_KEY", "fake_key")
@patch("openai.OpenAI")
def test_openai_json_mode_fallback(mock_openai_class):
    # Setup mock client
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    # We want create() to raise an Exception the first time (when response_format is provided)
    # and return a stream the second time.
    def mock_create(*args, **kwargs):
        if kwargs.get("response_format") == {"type": "json_object"}:
            raise Exception("JSON mode unsupported")

        # Second time (fallback), return a mock stream
        # A stream is an iterable of chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "{"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = '"status": "ok"'

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = "}"

        return [chunk1, chunk2, chunk3]

    mock_client.chat.completions.create.side_effect = mock_create

    # Trigger the function with a prompt containing "json"
    result = call_openai_llm("Please return a json response")

    # Assertions
    assert result == '{"status": "ok"}'
    assert mock_client.chat.completions.create.call_count == 2

    # First call: JSON mode
    first_call_kwargs = mock_client.chat.completions.create.call_args_list[0].kwargs
    assert first_call_kwargs.get("response_format") == {"type": "json_object"}

    # Second call: Stream fallback
    second_call_kwargs = mock_client.chat.completions.create.call_args_list[1].kwargs
    assert second_call_kwargs.get("stream") is True
