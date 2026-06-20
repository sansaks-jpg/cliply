"""Pluggable LLM backends for highlight ranking.

Lifted from shorts_generator/local/llm.py — adds Anthropic support.
"""
from typing import Callable

from ..config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    require_llm_key,
)

LLMFn = Callable[[str], str]


_LLM_TIMEOUT = 60  # seconds per LLM call


def call_openai_llm(prompt: str) -> str:
    from openai import OpenAI
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=_LLM_TIMEOUT)
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.7,
        stream=True,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = []
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
    return "".join(parts)


def call_anthropic_llm(prompt: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=require_llm_key())
    res = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )
    return res.content[0].text if res.content else ""


def call_gemini_llm(prompt: str) -> str:
    from google import genai
    from ..config import GEMINI_API_KEY, GEMINI_MODEL
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
            "max_output_tokens": 8192,
        },
    )
    return response.text or ""


def get_llm_fn() -> LLMFn:
    provider = (LLM_PROVIDER or "openai").strip().lower()
    if provider == "openai":
        return call_openai_llm
    if provider == "anthropic":
        return call_anthropic_llm
    if provider == "gemini":
        return call_gemini_llm
    raise ValueError(f"Unknown LLM_PROVIDER={provider!r}. Use 'openai', 'anthropic', or 'gemini'.")
