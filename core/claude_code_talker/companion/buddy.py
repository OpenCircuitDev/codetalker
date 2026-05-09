"""CCT-31 — BuddyClaude: parallel Anthropic Agent SDK session for AR companion.

Reads the user's main Claude Code session transcript for context but maintains
its own conversation. Read-only access to the user's session in v1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Literal

try:
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover
    anthropic = None  # tests can patch


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
    def __init__(
        self,
        *,
        user_session_id: str,
        transcript_path: Path,
        anthropic_api_key: str,
        model: str = "claude-sonnet-4-5",
    ):
        if not anthropic_api_key:
            raise ValueError("api_key required")
        self.user_session_id = user_session_id
        self.transcript_path = Path(transcript_path)
        self.api_key = anthropic_api_key
        self.model = model
        self.history: list[dict] = []
        self._client = None  # lazily constructed in inject()

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
        # Format context as a system-style intro (Anthropic API treats only
        # role=user/assistant; context goes inside system_prompt for v1).
        msgs: list[dict] = []
        for m in ctx[-6:]:  # last 6 to keep prompt small
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, (str, list)):
                msgs.append({"role": role, "content": content if isinstance(content, str) else "[non-text]"})
        msgs.extend(self.history)
        msgs.append({"role": "user", "content": user_text})
        return msgs

    async def inject(self, text: str) -> AsyncIterator[BuddyEvent]:
        if anthropic is None:
            yield BuddyEvent(kind="error", error="anthropic SDK not installed")
            return
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        messages = self._build_messages(text)
        # Append user turn to history immediately so callers can verify it
        # regardless of whether the stream produces text.
        self.history.append({"role": "user", "content": text})
        full_text_chunks: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.model,
                system=self._build_system_prompt(),
                messages=messages,
                max_tokens=512,
            ) as stream:
                async for evt in _iter_compat(stream):
                    et = getattr(evt, "type", None)
                    if et == "content_block_delta":
                        delta = getattr(evt, "delta", None)
                        chunk = getattr(delta, "text", "") if delta else ""
                        if chunk:
                            full_text_chunks.append(chunk)
                            yield BuddyEvent(kind="partial_text", text=chunk)
                    elif et == "message_stop":
                        full = "".join(full_text_chunks)
                        self.history.append({"role": "assistant", "content": full})
                        yield BuddyEvent(kind="final_text", text=full)
                        yield BuddyEvent(kind="done")
                        return
            # Stream ended without message_stop — still record history if we got chunks
            full = "".join(full_text_chunks)
            if full:
                self.history.append({"role": "assistant", "content": full})
                yield BuddyEvent(kind="final_text", text=full)
            yield BuddyEvent(kind="done")
        except Exception as e:  # pragma: no cover - real network errors
            yield BuddyEvent(kind="error", error=str(e))


class BuddyManager:
    def __init__(self, *, api_key: str, transcript_dir: Path, model: str = "claude-sonnet-4-5"):
        self.api_key = api_key
        self.transcript_dir = Path(transcript_dir)
        self.model = model
        self._buddies: dict[str, BuddyClaude] = {}

    def start(self, user_session_id: str) -> BuddyClaude:
        existing = self._buddies.get(user_session_id)
        if existing:
            return existing
        # Convention: Claude Code stores session transcripts at
        # transcript_dir / <session_id>.jsonl. Production codebases use the
        # SessionCatalog for resolution; we mirror that contract here.
        path = self.transcript_dir / f"{user_session_id}.jsonl"
        b = BuddyClaude(
            user_session_id=user_session_id,
            transcript_path=path,
            anthropic_api_key=self.api_key,
            model=self.model,
        )
        self._buddies[user_session_id] = b
        return b

    def get(self, user_session_id: str) -> BuddyClaude | None:
        return self._buddies.get(user_session_id)

    def stop(self, user_session_id: str) -> None:
        self._buddies.pop(user_session_id, None)

    def list_active(self) -> list[str]:
        return list(self._buddies.keys())


async def _iter_compat(stream):
    """Iterate over a stream that may be an async iterator or a sync one.

    The Anthropic SDK normally yields async events but tests mock it with
    sync iterables. We accept both shapes so unit tests don't need to
    construct full async machinery.
    """
    aiter = getattr(stream, "__aiter__", None)
    if aiter is not None:
        try:
            it = aiter() if not callable(getattr(aiter, "__call__", None)) is False else aiter()
        except TypeError:
            it = aiter
        # Peek if the returned iterator is async-iterable (has __anext__).
        if hasattr(it, "__anext__"):
            while True:
                try:
                    yield await it.__anext__()
                except StopAsyncIteration:
                    return
        # It's sync — fall through to sync iteration over the *result*.
        for evt in it:
            yield evt
        return
    for evt in stream:
        yield evt
