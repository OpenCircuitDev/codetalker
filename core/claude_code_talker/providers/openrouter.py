"""OpenRouter provider (any model via OpenAI-compatible endpoint)."""
from __future__ import annotations

import httpx

from claude_code_talker.providers.base import LLMProvider


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, model: str = "anthropic/claude-haiku-4-5"):
        if not api_key:
            raise ValueError("OpenRouterProvider requires api_key")
        self.api_key = api_key
        self.model = model

    async def complete(self, prompt: str, max_tokens: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise RuntimeError(f"openrouter request failed: {exc}") from exc
