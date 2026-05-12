"""CCT-31 + CCT-32 v0.1.0 polish — BuddyClaude: parallel LLM session for AR companion.

Reads the user's main Claude Code session transcript for context but maintains
its own conversation. Read-only access to the user's session in v1.

v0.1.0 polish: now uses OpenRouter's OpenAI-compatible /chat/completions
endpoint (httpx + SSE) instead of the Anthropic SDK directly. This aligns
the buddy with the rest of the codebase's provider abstraction
(providers/openrouter.py) and lets a single OpenRouter key power both
narration and the AR-companion buddy. The default model is
`anthropic/claude-sonnet-4-5` which OpenRouter routes to Anthropic;
override via the `model` constructor arg for Gemini, GPT-4, etc.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


@dataclass
class BuddyEvent:
    kind: Literal["partial_text", "final_text", "tool_use", "done", "error"]
    text: str = ""
    error: str | None = None


def read_recent_transcript(path: Path, max_messages: int = 20) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and "role" in msg:
                out.append(msg)
    except OSError:
        return []
    return out[-max_messages:]


class BuddyClaude:
    """Buddy LLM session using OpenRouter chat completions.

    The constructor keeps the `anthropic_api_key` parameter name for backward
    compatibility with callers wired before the v0.1.0 refactor, but the value
    is treated as a generic Bearer token. Supply an OpenRouter key (preferred)
    or a direct Anthropic key with `base_url=https://api.anthropic.com/v1`
    (though the request shape is OpenAI-compatible so direct Anthropic auth
    will not work without further changes).
    """

    def __init__(
        self,
        *,
        user_session_id: str,
        transcript_path: Path,
        anthropic_api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
    ):
        if not anthropic_api_key:
            raise ValueError("api_key required")
        self.user_session_id = user_session_id
        self.transcript_path = Path(transcript_path)
        self.api_key = anthropic_api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.history: list[dict] = []
        self._client: httpx.AsyncClient | None = None

    def _build_system_prompt(self) -> str:
        return (
            "You are an AR voice companion. The user is wearing AR glasses "
            f"controlling another Claude Code session whose transcript is at "
            f"{self.transcript_path}. Read the recent transcript before "
            "answering. Keep responses short and conversational; they will "
            "be spoken aloud through the user's glasses speaker."
        )

    def _build_messages(self, user_text: str) -> list[dict]:
        ctx = read_recent_transcript(self.transcript_path, max_messages=20)
        msgs: list[dict] = [{"role": "system", "content": self._build_system_prompt()}]
        for m in ctx[-6:]:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, (str, list)):
                msgs.append({
                    "role": role,
                    "content": content if isinstance(content, str) else "[non-text]",
                })
        msgs.extend(self.history)
        msgs.append({"role": "user", "content": user_text})
        return msgs

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=2, keepalive_expiry=300),
            )
        return self._client

    async def inject(self, text: str) -> AsyncIterator[BuddyEvent]:
        client = await self._ensure_client()
        messages = self._build_messages(text)
        # Append user turn immediately so callers can verify it even if the
        # network call fails before producing any output.
        self.history.append({"role": "user", "content": text})
        full_text_chunks: list[str] = []
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 512,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = data["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError):
                        delta = None
                    if delta:
                        full_text_chunks.append(delta)
                        yield BuddyEvent(kind="partial_text", text=delta)
            full = "".join(full_text_chunks)
            if full:
                self.history.append({"role": "assistant", "content": full})
                yield BuddyEvent(kind="final_text", text=full)
            yield BuddyEvent(kind="done")
        except Exception as e:  # pragma: no cover - real network errors
            yield BuddyEvent(kind="error", error=str(e))


class BuddyManager:
    def __init__(
        self,
        *,
        api_key: str,
        transcript_dir: Path,
        model: str = DEFAULT_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
    ):
        self.api_key = api_key
        self.transcript_dir = Path(transcript_dir)
        self.model = model
        self.base_url = base_url
        self._buddies: dict[str, BuddyClaude] = {}

    def start(self, user_session_id: str) -> BuddyClaude:
        existing = self._buddies.get(user_session_id)
        if existing:
            return existing
        path = self.transcript_dir / f"{user_session_id}.jsonl"
        b = BuddyClaude(
            user_session_id=user_session_id,
            transcript_path=path,
            anthropic_api_key=self.api_key,
            model=self.model,
            base_url=self.base_url,
        )
        self._buddies[user_session_id] = b
        return b

    def get(self, user_session_id: str) -> BuddyClaude | None:
        return self._buddies.get(user_session_id)

    def stop(self, user_session_id: str) -> None:
        self._buddies.pop(user_session_id, None)

    def list_active(self) -> list[str]:
        return list(self._buddies.keys())
