import unittest
from unittest.mock import patch, MagicMock
from app.engine.llm import call_anthropic_llm

class TestAnthropicLLM(unittest.TestCase):
    @patch('app.engine.llm.require_llm_key')
    @patch('anthropic.Anthropic')
    def test_call_anthropic_llm_no_markers(self, MockAnthropic, mock_require_key):
        # Arrange
        mock_require_key.return_value = 'test_key'
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='response text')]
        mock_client.messages.create.return_value = mock_response

        prompt = "This is a simple prompt without markers."

        # Act
        result = call_anthropic_llm(prompt)

        # Assert
        self.assertEqual(result, 'response text')
        mock_client.messages.create.assert_called_once()
        args, kwargs = mock_client.messages.create.call_args
        self.assertEqual(kwargs['system'][0]['text'], prompt)
        self.assertEqual(kwargs['messages'][0]['content'], prompt)

    @patch('app.engine.llm.require_llm_key')
    @patch('anthropic.Anthropic')
    def test_call_anthropic_llm_narrative_map(self, MockAnthropic, mock_require_key):
        # Arrange
        mock_require_key.return_value = 'test_key'
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='narrative response')]
        mock_client.messages.create.return_value = mock_response

        system_part = "System instructions."
        user_part = "The narrative map content."
        prompt = f"{system_part} Narrative map: {user_part}"

        # Act
        result = call_anthropic_llm(prompt)

        # Assert
        self.assertEqual(result, 'narrative response')
        mock_client.messages.create.assert_called_once()
        args, kwargs = mock_client.messages.create.call_args
        self.assertEqual(kwargs['system'][0]['text'], system_part)
        self.assertEqual(kwargs['messages'][0]['content'], f"Narrative map:\n{user_part}")

    @patch('app.engine.llm.require_llm_key')
    @patch('anthropic.Anthropic')
    def test_call_anthropic_llm_transcript(self, MockAnthropic, mock_require_key):
        # Arrange
        mock_require_key.return_value = 'test_key'
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='transcript response')]
        mock_client.messages.create.return_value = mock_response

        system_part = "System instructions."
        user_part = "The transcript content."
        prompt = f"{system_part} Transcript: {user_part}"

        # Act
        result = call_anthropic_llm(prompt)

        # Assert
        self.assertEqual(result, 'transcript response')
        mock_client.messages.create.assert_called_once()
        args, kwargs = mock_client.messages.create.call_args
        self.assertEqual(kwargs['system'][0]['text'], system_part)
        self.assertEqual(kwargs['messages'][0]['content'], f"Transcript:\n{user_part}")

    @patch('app.engine.llm.require_llm_key')
    @patch('anthropic.Anthropic')
    def test_call_anthropic_llm_caching(self, MockAnthropic, mock_require_key):
        # Arrange
        mock_require_key.return_value = 'test_key'
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='caching response')]
        mock_client.messages.create.return_value = mock_response

        # Create a long system text > 1024 chars
        system_part = "A" * 1025
        prompt = f"{system_part} Transcript: The content"

        # Act
        result = call_anthropic_llm(prompt)

        # Assert
        self.assertEqual(result, 'caching response')
        args, kwargs = mock_client.messages.create.call_args
        self.assertEqual(kwargs['system'][0]['cache_control']['type'], 'ephemeral')

    @patch('app.engine.llm.require_llm_key')
    @patch('anthropic.Anthropic')
    def test_call_anthropic_llm_empty_response(self, MockAnthropic, mock_require_key):
        # Arrange
        mock_require_key.return_value = 'test_key'
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [] # Empty content
        mock_client.messages.create.return_value = mock_response

        prompt = "Some prompt"

        # Act
        result = call_anthropic_llm(prompt)

        # Assert
        self.assertEqual(result, '')

if __name__ == '__main__':
    unittest.main()
