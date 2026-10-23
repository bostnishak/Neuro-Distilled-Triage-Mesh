"""Async client for any OpenAI-compatible chat-completions endpoint.

Works with OpenAI, Azure OpenAI (via compatible gateway), vLLM, Ollama,
LiteLLM, TGI, etc. Used as the *Teacher* LLM, the critic, the VLM image
inspector and the neuro-symbolic translator / planner.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from core.config import Settings

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMUnavailableError(LLMError):
    """LLM is disabled or not configured."""


class LLMTransientError(LLMError):
    """Retryable failure (timeouts, 429, 5xx)."""


class LLMResponseError(LLMError):
    """Non-retryable failure (4xx, malformed payload)."""


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating code fences / prose."""
    candidate = _FENCE_RE.sub("", text.strip())
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise LLMResponseError(f"No JSON object in LLM response: {text[:300]!r}") from None
        try:
            parsed = json.loads(candidate[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"Invalid JSON in LLM response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseError("LLM response JSON is not an object")
    return parsed


class LLMClient:
    """Minimal, resilient chat-completions client."""

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.llm_enabled
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        self._model = settings.llm_model
        self._max_retries = settings.llm_max_retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    @property
    def available(self) -> bool:
        return self._enabled and bool(self._base_url)

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = True,
    ) -> str:
        """Return the assistant message content. Retries transient errors with jittered backoff."""
        if not self.available:
            raise LLMUnavailableError("LLM is disabled (set LLM_ENABLED=true and LLM_BASE_URL)")

        body: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(LLMTransientError),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential_jitter(initial=1, max=20),
            reraise=True,
        ):
            with attempt:
                try:
                    resp = await self._client.post(f"{self._base_url}/chat/completions", json=body,
                                                   headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    raise LLMTransientError(f"LLM transport error: {exc}") from exc
                if resp.status_code in (408, 409, 429) or resp.status_code >= 500:
                    raise LLMTransientError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
                if resp.status_code >= 400:
                    raise LLMResponseError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
                try:
                    content = resp.json()["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise LLMResponseError(f"Unexpected LLM payload: {resp.text[:300]}") from exc
                if not isinstance(content, str) or not content.strip():
                    raise LLMResponseError("LLM returned empty content")
                return content
        raise LLMError("unreachable")  # pragma: no cover

    async def chat_json(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Chat and parse the response as a JSON object."""
        return extract_json(await self.chat(messages, json_mode=True, **kwargs))
