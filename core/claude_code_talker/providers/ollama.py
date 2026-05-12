"""Ollama LLM provider (local HTTP API)."""
from __future__ import annotations

from threading import Lock

import httpx

from claude_code_talker.providers.base import LLMProvider

# ---------------------------------------------------------------------------
# Persistent connection pool (Phase 13.9b Task 6)
# ---------------------------------------------------------------------------
# Ollama runs locally; HTTP/2 may not be supported by the daemon, but a
# persistent client still saves connection-setup overhead between narrations.

_CLIENT: httpx.AsyncClient | None = None
_CLIENT_LOCK = Lock()


def _get_client() -> httpx.AsyncClient:
    """Return the shared httpx client, creating it on first call.

    A persistent connection pool eliminates per-request connection-setup
    overhead even for local Ollama endpoints. HTTP/2 is attempted but falls
    back to HTTP/1.1 if the ``h2`` package is not installed.
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


class OllamaProvider(LLMProvider):
    """Talks to a local Ollama daemon via its HTTP API."""

    name = "ollama"

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "llama3.2:1b"):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    async def complete(self, prompt: str, max_tokens: int, *, system: str | None = None) -> str:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if system:
            # Ollama's native `system` param ships the system prompt
            # separately so model templates use the right slot.
            payload["system"] = system
        client = _get_client()
        resp = await client.post(f"{self.endpoint}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
