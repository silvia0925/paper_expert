"""Shared async LLM call utility.

Supports OpenAI-compatible API (cloud) and Ollama (local) with automatic fallback.
Used by review engine, direction advisor, and domain expert.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from paper_expert.core.config import PaperExpertConfig

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE = 3.0
_OLLAMA_BASE = "http://localhost:11434"


async def _ollama_chat(
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float = 0.3,
) -> str:
    """Call Ollama local chat API. Returns response text or empty string."""
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{_OLLAMA_BASE}/api/chat", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
        except httpx.HTTPError as e:
            logger.warning(
                "Ollama call attempt %d failed: %s", attempt + 1, str(e)[:80]
            )
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
    return ""


async def _openai_chat(
    api_key: str,
    api_base: str,
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    """Call OpenAI-compatible chat API. Returns response text or empty string."""
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 429:
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.info(
                        "LLM rate limit, waiting %.0fs (attempt %d)",
                        wait, attempt + 1,
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except httpx.HTTPError as e:
            logger.warning(
                "OpenAI call attempt %d failed: %s", attempt + 1, str(e)[:80]
            )
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
    return ""


async def llm_chat(
    messages: list[dict[str, str]],
    config: PaperExpertConfig | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Call an LLM with automatic cloud/local fallback.

    Priority: 1) OpenAI cloud with api_key  2) Ollama local

    Args:
        messages: Chat messages [{"role": "user", "content": "..."}].
        config: PaperExpertConfig. Loaded if None.
        model: Override model name (cloud or local).
        temperature: Sampling temperature.
        max_tokens: Max response tokens (OpenAI only).

    Returns:
        The assistant's response text. Empty string on all failures.
    """
    if config is None:
        config = PaperExpertConfig.load()

    # ── Path 1: OpenAI cloud (when api key is configured) ──
    api_key = config.api_keys.openai
    if api_key:
        api_base = config.llm.api_base or "https://api.openai.com/v1"
        model_name = model or config.llm.cloud_model
        if model_name.startswith("openai/"):
            model_name = model_name[len("openai/"):]
        result = await _openai_chat(
            api_key, api_base, model_name, messages, temperature, max_tokens
        )
        if result:
            return result
        logger.info("OpenAI call failed, falling back to local Ollama")

    # ── Path 2: Ollama local ──
    local_model = model
    if not local_model:
        local = config.llm.local_model
        if local.startswith("ollama/"):
            local = local[len("ollama/"):]
        local_model = local
    if not local_model:
        logger.error(
            "No LLM available. Set api_keys.openai for cloud or "
            "llm.local_model for local Ollama."
        )
        return ""

    logger.info("Using local Ollama model: %s", local_model)
    return await _ollama_chat(local_model, messages, temperature)


async def llm_chat_json(
    messages: list[dict[str, str]],
    config: PaperExpertConfig | None = None,
    model: str | None = None,
) -> Any:
    """Call LLM and parse response as JSON.

    Returns parsed JSON object, or empty dict/list on failure.
    """
    response = await llm_chat(messages, config=config, model=model)
    if not response:
        return {}

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.debug("Failed to parse LLM response as JSON: %s", text[:200])
        return {}
