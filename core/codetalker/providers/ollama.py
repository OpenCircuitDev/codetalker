"""Ollama LLM provider (local HTTP API)."""
from __future__ import annotations

import httpx

from codetalker.providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    """Talks to a local Ollama daemon via its HTTP API."""

    name = "ollama"

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "llama3.2:1b"):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    async def complete(self, prompt: str, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.endpoint}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
