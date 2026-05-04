"""Per-session running focus for narrator context enrichment.

Tracks: recent user prompts, files-in-play, an LLM-generated task header,
a cumulative narrative summary, and the latest "Audible summary:" line.
The narrator injects ``render_block()`` into its prompt so it can produce
narrations that reference the session's continuity (the WHY + CONTEXT).
"""
from __future__ import annotations

import ast
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field


_HEADER_REFRESH_AFTER_NARRATIONS = 5
_HEADER_REFRESH_AFTER_SECONDS = 60.0
_FILES_CAP = 8
_PROMPTS_CAP = 3


# ---------------------------------------------------------------------------
# Phase 13.9c Task 8: "Audible summary:" verbatim detection
# ---------------------------------------------------------------------------

_AUDIBLE_SUMMARY_PATTERN = re.compile(
    r"^audible summary[:\s]+(.+?)(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def extract_audible_summary(text: str) -> str:
    """Return the most recent 'Audible summary:' line from text, or empty."""
    if not text:
        return ""
    matches = _AUDIBLE_SUMMARY_PATTERN.findall(text)
    return matches[-1].strip() if matches else ""


# ---------------------------------------------------------------------------
# Phase 13.9c Task 8: narrative summary prompt template
# ---------------------------------------------------------------------------

_NARRATIVE_SUMMARY_PROMPT_TEMPLATE = """\
You maintain a running 1-paragraph summary of what a Claude Code session has been
working on. Update the summary based on the previous version + the recent
assistant prose.

PREVIOUS SUMMARY:
{previous}

RECENT ASSISTANT PROSE (newest last):
{prose}

Output ONLY the updated summary as a single paragraph (≤500 chars). Do not
include preamble or quotes. The summary should be in past/present tense and
describe the cumulative arc — what's been investigated, decided, built,
or attempted across the session so far.
"""


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
    # Phase 13.8 R5: dirty flag — set by record_user_prompt so the task header
    # refreshes eagerly on the next narration cycle after a new user prompt.
    dirty: bool = False
    # Phase 13.9a Task 3: in_progress activeForm strings from the latest TodoWrite,
    # capped at 5.  Populated by record_todos(); injected into render_block().
    current_todos: list = field(default_factory=list)
    # Phase 13.9c Task 8: persistent narrative summary (cumulative paragraph ≤500 chars)
    narrative_summary: str = ""
    summary_last_refreshed_at: float = 0.0
    summary_narrations_since: int = 0  # increments per narrate; resets on refresh
    # Phase 13.9c Task 8: latest "Audible summary:" line detected from assistant prose
    audible_summary_line: str = ""

    def record_user_prompt(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        # Dedup against the most-recent entry
        if self.recent_user_prompts and self.recent_user_prompts[-1] == text:
            return
        self.recent_user_prompts.append(text)
        self.dirty = True  # Phase 13.8 R5: mark stale on every new prompt

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

    def record_todos(self, todos: list) -> None:
        """Extract in_progress items' activeForm into current_todos. Caps at 5."""
        in_progress = []
        for t in todos:
            if not isinstance(t, dict):
                continue
            if t.get("status") == "in_progress":
                af = t.get("activeForm")
                if af:
                    in_progress.append(str(af)[:120])
        self.current_todos = in_progress[:5]

    def should_refresh_header(self) -> bool:
        if not self.task_header:
            return True
        # Phase 13.8 R5: a new user prompt marks the focus dirty so the header
        # refreshes on the very next narration cycle.
        if self.dirty:
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
            self.dirty = False  # Phase 13.8 R5: clear after successful refresh

    async def refresh_narrative_summary(self, provider, recent_prose: list[str]) -> None:
        """Update the cumulative narrative summary via a cheap LLM call.

        Fire-and-forget: caller should use asyncio.create_task(). On failure,
        the stale summary is preserved (never blanked).
        """
        prompt = _NARRATIVE_SUMMARY_PROMPT_TEMPLATE.format(
            previous=self.narrative_summary or "(no prior summary)",
            prose="\n---\n".join(recent_prose[-10:]) or "(no recent prose)",
        )
        try:
            raw = await provider.complete(prompt, max_tokens=200)
        except Exception as e:
            logging.debug("narrative summary refresh failed: %s", e)
            return
        summary = (raw or "").strip().strip('"').strip("'")
        if summary:
            self.narrative_summary = summary[:500]
            self.summary_last_refreshed_at = time.time()
            self.summary_narrations_since = 0

    def render_block(self) -> str:
        has_anything = bool(
            self.task_header or self.recent_user_prompts or self.files_in_play
            or self.narrative_summary or self.audible_summary_line
        )
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
        if self.current_todos:
            lines.append(f"- Currently doing: {', '.join(self.current_todos)}")
        # Phase 13.9c Task 8: narrative summary + audible summary
        if self.narrative_summary:
            lines.append(f"- Session arc so far: {self.narrative_summary}")
        if self.audible_summary_line:
            lines.append(
                f'- AGENT EXPLICIT NARRATION (use near-verbatim): "{self.audible_summary_line}"'
            )
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

    def record_assistant_prose(self, session_id: str, prose: str) -> None:
        """Called when new assistant prose lands. Detects 'Audible summary:' lines."""
        f = self.get_or_create(session_id)
        line = extract_audible_summary(prose)
        if line:
            f.audible_summary_line = line[:500]

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
            # Phase 13.9a Task 3: TodoWrite extraction
            if tool == "TodoWrite":
                raw_str = (raw or "").strip()
                if isinstance(raw, dict):
                    parsed = raw
                elif isinstance(raw_str, str) and raw_str.startswith("{"):
                    try:
                        parsed = ast.literal_eval(raw_str)
                    except (ValueError, SyntaxError):
                        parsed = None
                else:
                    parsed = None
                if isinstance(parsed, dict) and isinstance(parsed.get("todos"), list):
                    f.record_todos(parsed["todos"])


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
