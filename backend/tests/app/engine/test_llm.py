import pytest
from unittest.mock import patch

from app.engine.llm import get_llm_fn, call_openai_llm, call_anthropic_llm, call_gemini_llm

@pytest.mark.parametrize("provider_value, expected_fn", [
    ("openai", call_openai_llm),
    ("anthropic", call_anthropic_llm),
    ("gemini", call_gemini_llm),
    ("  oPeNaI ", call_openai_llm),
    ("  aNtHroPiC  ", call_anthropic_llm),
    ("GeMiNi", call_gemini_llm),
    ("", call_openai_llm),
    (None, call_openai_llm),
])
def test_get_llm_fn_valid_providers(provider_value, expected_fn):
    with patch('app.engine.llm.LLM_PROVIDER', provider_value):
        assert get_llm_fn() == expected_fn

def test_get_llm_fn_unknown():
    with patch('app.engine.llm.LLM_PROVIDER', 'unknown'):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER='unknown'"):
            get_llm_fn()

def test_get_llm_fn_unknown_whitespace():
    with patch('app.engine.llm.LLM_PROVIDER', '  bad_provider  '):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER='bad_provider'"):
            get_llm_fn()
