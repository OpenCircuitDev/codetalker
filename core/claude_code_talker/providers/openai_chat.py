"""OpenAI as an LLM (chat completions) provider — separate from the OpenAI TTS engine."""
from __future__ import annotations

import json
from threading import Lock
from typing import AsyncIterator

import httpx

from claude_code_talker.providers.base import LLMProvider

# ---------------------------------------------------------------------------
# Persistent connection pool (Phase 13.9b Task 6)
# ---------------------------------------------------------------------------

_CLIENT: httpx.AsyncClient | None = None
_CLIENT_LOCK = Lock()


def _get_client() -> httpx.AsyncClient:
    """Return the shared httpx client, creating it on first call.

    Persistent connection pool with HTTP/2 + 5-minute keepalive eliminates
    cold-connect overhead (200-400ms TLS handshake) on every narration call.
    Falls back to HTTP/1.1 keepalive if the ``h2`` package is not installed.
    """
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _limits = httpx.Limits(
                    max_keepalive_connections=2,
                    keepalive_expiry=300,
                )
                _timeout = httpx.Timeout(60.0, connect=10.0)
                try:
                    _CLIENT = httpx.AsyncClient(
                        http2=True,
                        timeout=_timeout,
                        limits=_limits,
                    )
                except ImportError:
                    _CLIENT = httpx.AsyncClient(
                        http2=False,
                        timeout=_timeout,
                        limits=_limits,
                    )
    return _CLIENT


class OpenAIChatProvider(LLMProvider):
    name = "openai"
    supports_streaming = True
    BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OpenAIChatProvider requires api_key")
        self.api_key = api_key
        self.model = model

    @staticmethod
    def _build_messages(prompt: str, system: str | None) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    async def complete(self, prompt: str, max_tokens: int, *, system: str | None = None) -> str:
        try:
            client = _get_client()
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": self._build_messages(prompt, system),
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise RuntimeError(f"openai request failed: {exc}") from exc

    async def stream(self, prompt: str, max_tokens: int, *, system: str | None = None) -> AsyncIterator[str]:
        """Stream text deltas via OpenAI SSE."""
        try:
            client = _get_client()
            async with client.stream(
                "POST",
                f"{self.BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": self._build_messages(prompt, system),
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        return
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = data["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError):
                        continue
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise RuntimeError(f"openai stream failed: {exc}") from exc
