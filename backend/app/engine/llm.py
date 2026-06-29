"""Pluggable LLM backends for highlight ranking.

Lifted from shorts_generator/local/llm.py — adds Anthropic support.
"""
import logging
import time
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

logger = logging.getLogger(__name__)

LLMFn = Callable[[str], str]


_LLM_TIMEOUT = 60  # seconds per LLM call
_LLM_MAX_RETRIES = 3
_LLM_RETRY_DELAY = 2  # seconds, doubles each retry


def call_openai_llm(prompt: str) -> str:
    from openai import OpenAI
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=_LLM_TIMEOUT)

    messages = [{"role": "user", "content": prompt}]
    last_err: Exception | None = None

    for attempt in range(_LLM_MAX_RETRIES):
        try:
            # Defensively attempt JSON response format if JSON is requested in the prompt
            if "json" in prompt.lower():
                try:
                    res = client.chat.completions.create(
                        model=OPENAI_MODEL,
                        temperature=0.7,
                        messages=messages,
                        response_format={"type": "json_object"},
                        timeout=_LLM_TIMEOUT,
                    )
                    return res.choices[0].message.content or ""
                except Exception as je:
                    json_status = getattr(je, "status_code", None)
                    # Only fall back to stream if JSON format is genuinely unsupported (400/422)
                    # Don't swallow 404/429/5xx — those are real errors that need retry
                    if json_status and json_status not in (400, 422):
                        raise
                    logger.warning(
                        "JSON mode unsupported, falling back to stream: %s", je
                    )

            # Standard stream fallback
            stream = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.7,
                stream=True,
                messages=messages,
            )
            parts = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    parts.append(chunk.choices[0].delta.content)
            return "".join(parts)
        except Exception as e:
            last_err = e
            status = getattr(e, "status_code", None)
            # Only retry on transient errors (429, 500+). 404 = endpoint/model not found, don't retry.
            if status and status not in (429,) and status < 500:
                raise
            delay = _LLM_RETRY_DELAY * (2 ** attempt)
            logger.warning(
                "LLM call failed (attempt %d/%d, status=%s), retrying in %ds: %s",
                attempt + 1, _LLM_MAX_RETRIES, status, delay, e,
            )
            time.sleep(delay)

    raise RuntimeError(f"LLM call failed after {_LLM_MAX_RETRIES} attempts: {last_err}") from last_err


def call_anthropic_llm(prompt: str) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=require_llm_key())
    
    # Split the prompt into static system instructions and dynamic content (transcript/narrative map)
    # for optimal byte-for-byte prompt caching alignment.
    system_text = prompt
    user_text = ""
    
    split_marker = "Narrative map:"
    if split_marker in prompt:
        parts = prompt.split(split_marker, 1)
        system_text = parts[0].strip()
        user_text = split_marker + "\n" + parts[1].strip()
    else:
        split_marker_transcript = "Transcript:"
        if split_marker_transcript in prompt:
            parts = prompt.split(split_marker_transcript, 1)
            system_text = parts[0].strip()
            user_text = split_marker_transcript + "\n" + parts[1].strip()
            
    system_blocks = [{"type": "text", "text": system_text}]
    # Mark system blocks for ephemeral caching if system prompt is reasonably large
    if len(system_text) > 1024:
        system_blocks[0]["cache_control"] = {"type": "ephemeral"}
        
    messages = []
    if user_text:
        messages.append({"role": "user", "content": user_text})
    else:
        messages.append({"role": "user", "content": prompt})
        
    res = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0.7,
        system=system_blocks,
        messages=messages,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
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
    import os
    from ..config import GEMINI_API_KEY

    primary_provider = (LLM_PROVIDER or "openai").strip().lower()
    
    # Tentukan urutan fallback provider secara logis
    providers_chain = [primary_provider]
    for p in ["openai", "gemini", "anthropic"]:
        if p not in providers_chain:
            providers_chain.append(p)

    def call_llm_with_fallback(prompt: str) -> str:
        last_error = None
        
        for provider in providers_chain:
            # Verifikasi ketersediaan API key sebelum mencoba memanggil provider tersebut
            if provider == "openai" and not OPENAI_API_KEY:
                logger.debug("Skipping OpenAI fallback: OPENAI_API_KEY is not set.")
                continue
            if provider == "gemini" and not (GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")):
                logger.debug("Skipping Gemini fallback: GEMINI_API_KEY is not set.")
                continue
            if provider == "anthropic" and not ANTHROPIC_API_KEY:
                logger.debug("Skipping Anthropic fallback: ANTHROPIC_API_KEY is not set.")
                continue

            try:
                if provider != primary_provider:
                    logger.warning(
                        f"Circuit Breaker Triggered: Primary provider '{primary_provider}' failed. "
                        f"Attempting fallback to '{provider}'..."
                    )
                
                if provider == "openai":
                    return call_openai_llm(prompt)
                elif provider == "gemini":
                    return call_gemini_llm(prompt)
                elif provider == "anthropic":
                    return call_anthropic_llm(prompt)
            except Exception as e:
                logger.error(f"LLM provider '{provider}' failed during execution: {e}")
                last_error = e

        raise RuntimeError(
            f"All configured LLM providers failed. Primary: {primary_provider}. "
            f"Providers chain attempted: {providers_chain}. Last error: {last_error}"
        ) from last_error

    return call_llm_with_fallback
