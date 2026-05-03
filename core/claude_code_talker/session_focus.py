"""Per-session running focus for narrator context enrichment.

Tracks: recent user prompts, files-in-play, an LLM-generated task header.
The narrator injects ``render_block()`` into its prompt so it can produce
narrations that reference the session's continuity (the WHY + CONTEXT).
"""
from __future__ import annotations

import ast
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field


_HEADER_REFRESH_AFTER_NARRATIONS = 5
_HEADER_REFRESH_AFTER_SECONDS = 60.0
_FILES_CAP = 8
_PROMPTS_CAP = 3


_HEADER_PROMPT_TEMPLATE = """\
Summarize what the user is currently working on in ONE short sentence (max 20 words).
Use a verb phrase form starting with a gerund or active verb (e.g. "implementing JWT middleware in the auth pipeline").
Do NOT mention the user's name. Do NOT add preamble. Output the sentence only, no quotes.

RECENT USER REQUESTS:
{prompts}

FILES IN PLAY:
{files}
"""


@dataclass
class SessionFocus:
    recent_user_prompts: deque = field(default_factory=lambda: deque(maxlen=_PROMPTS_CAP))
    files_in_play: dict = field(default_factory=dict)
    task_header: str = ""
    task_header_at: float = 0.0
    narrations_since_refresh: int = 0

    def record_user_prompt(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        # Dedup against the most-recent entry
        if self.recent_user_prompts and self.recent_user_prompts[-1] == text:
            return
        self.recent_user_prompts.append(text)

    def record_file_touch(self, path: str, *, timestamp: float | None = None) -> None:
        path = (path or "").strip()
        if not path:
            return
        ts = time.time() if timestamp is None else timestamp
        self.files_in_play[path] = ts
        # Evict oldest if over cap
        if len(self.files_in_play) > _FILES_CAP:
            oldest = sorted(self.files_in_play.items(), key=lambda kv: kv[1])
            for k, _ in oldest[: len(self.files_in_play) - _FILES_CAP]:
                self.files_in_play.pop(k, None)

    def should_refresh_header(self) -> bool:
        if not self.task_header:
            return True
        if self.narrations_since_refresh >= _HEADER_REFRESH_AFTER_NARRATIONS:
            return True
        if time.time() - self.task_header_at >= _HEADER_REFRESH_AFTER_SECONDS:
            return True
        return False

    async def refresh_header(self, provider) -> None:
        prompts = "\n".join(f"- {p}" for p in self.recent_user_prompts) or "(none)"
        files = "\n".join(f"- {p}" for p in self.files_in_play) or "(none)"
        prompt = _HEADER_PROMPT_TEMPLATE.format(prompts=prompts, files=files)
        try:
            raw = await provider.complete(prompt, max_tokens=60)
        except Exception as e:
            logging.debug("session focus header refresh failed: %s", e)
            return
        header = (raw or "").strip().strip('"').strip("'")
        if header:
            self.task_header = header[:200]
            self.task_header_at = time.time()
            self.narrations_since_refresh = 0

    def render_block(self) -> str:
        has_anything = bool(self.task_header or self.recent_user_prompts or self.files_in_play)
        if not has_anything:
            return ""
        lines = ["", "SESSION FOCUS:"]
        if self.task_header:
            lines.append(f"- Current task: {self.task_header}")
        if self.recent_user_prompts:
            lines.append("- Recent user requests:")
            for p in list(self.recent_user_prompts):
                lines.append(f"  • {p[:200]}")
        if self.files_in_play:
            # Newest first
            ordered = sorted(self.files_in_play.items(), key=lambda kv: -kv[1])
            files = ", ".join(p for p, _ in ordered)
            lines.append(f"- Files in play: {files}")
        return "\n".join(lines)


class SessionFocusRegistry:
    """Thread-safe per-session SessionFocus map."""

    def __init__(self):
        self._by_session: dict[str, SessionFocus] = {}
        self._lock = threading.RLock()

    def get_or_create(self, session_id: str) -> SessionFocus:
        with self._lock:
            f = self._by_session.get(session_id)
            if f is None:
                f = SessionFocus()
                self._by_session[session_id] = f
            return f

    def on_event(self, session_id: str, event) -> None:
        """Update focus for ``session_id`` from a single Event."""
        f = self.get_or_create(session_id)
        if event.type == "USER_PROMPT":
            text = (event.metadata.get("text") or "")[:200]
            f.record_user_prompt(text)
        elif event.type == "PRE_TOOL":
            tool = event.metadata.get("tool_name", "")
            raw = event.metadata.get("input", "")
            file_path = _extract_file_path(tool, raw)
            if file_path:
                f.record_file_touch(file_path, timestamp=event.timestamp)


_FILE_PATH_TOOLS = {"Edit", "Write", "Read", "NotebookEdit", "MultiEdit"}


def _extract_file_path(tool_name: str, raw_input: str) -> str:
    if tool_name not in _FILE_PATH_TOOLS:
        return ""
    raw = (raw_input or "").strip()
    if not raw or not raw.startswith("{"):
        return ""
    try:
        v = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return ""
    if not isinstance(v, dict):
        return ""
    fp = v.get("file_path") or v.get("notebook_path") or ""
    return str(fp).strip()
