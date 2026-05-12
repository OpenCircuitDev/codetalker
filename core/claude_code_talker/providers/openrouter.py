"""OpenRouter provider (any model via OpenAI-compatible endpoint)."""
from __future__ import annotations

import json
from threading import Lock
from typing import AsyncIterator

import httpx

from claude_code_talker.providers.base import LLMProvider

# ---------------------------------------------------------------------------
# Persistent connection pool (Phase 13.9b Task 6)
# ---------------------------------------------------------------------------
# A single module-level httpx.AsyncClient is created on first use and reused
# for all subsequent requests.  This eliminates the 200-400ms TLS handshake
# that was paid on every narration call when the client was created per-request.
#
# HTTP/2 multiplexing is enabled when the `h2` package is available; falls back
# to HTTP/1.1 keepalive (still a win over per-request clients).
#
# The singleton is process-lifetime — the httpx connection pool manages
# keepalive expiry and idle-connection cleanup internally.
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
                    # h2 not installed; HTTP/1.1 keepalive is still better than
                    # creating a fresh client per request.
                    _CLIENT = httpx.AsyncClient(
                        http2=False,
                        timeout=_timeout,
                        limits=_limits,
                    )
    return _CLIENT


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    supports_streaming = True
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, model: str = "google/gemini-2.0-flash-001"):
        if not api_key:
            raise ValueError("OpenRouterProvider requires api_key")
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
            raise RuntimeError(f"openrouter request failed: {exc}") from exc

    async def stream(self, prompt: str, max_tokens: int, *, system: str | None = None) -> AsyncIterator[str]:
        """Stream text deltas via OpenRouter's OpenAI-compatible SSE."""
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
            raise RuntimeError(f"openrouter stream failed: {exc}") from exc
