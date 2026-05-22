"""Parse Claude Code's JSONL transcript files into per-turn structures."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

# Conservative URL pattern — matches http(s) and bare www.* URLs.
# Replace each match with the placeholder "[link]" so the narrator can
# acknowledge a link existed without trying to pronounce it.
# Note: intentionally does NOT match plain dotted tokens like "version 1.2.3"
# because those lack the "://" scheme or "www." prefix.
_URL_PATTERN = re.compile(
    r"https?://\S+|www\.[^\s]+",
    re.IGNORECASE,
)

# Markdown-link form: [display text](url-or-path) — collapses to just the
# display text. The narrator gets the human-readable label without the
# parenthesized path being recited.
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Bare file-path tokens with directory separators — Windows-style and POSIX.
# Collapses to the basename so the narrator says "live.py" instead of
# spelling out "C:/Users/.../modes/live.py" character by character.
# Conservative: only matches paths containing at least one separator
# (avoids matching plain words). Skips tokens that are part of a URL match.
_FILE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/])?(?:[\w\-.]+[\\/])+[\w\-.]+",
)

# Backtick code-span: `token` — Phase 13.8 R1.
# Captures the content inside single backticks (non-greedy, no newlines).
_BACKTICK_SPAN = re.compile(r"`([^`\n]+)`")

# Long numeric token: 7 or more consecutive digits as a standalone word.
# Catches Unix timestamps, SHA-prefix-like IDs, etc.
# Phase 13.8 R2.
_LONG_NUMERIC = re.compile(r"\b\d{7,}\b")


def _normalize_backtick_span(content: str) -> str:
    """Normalise the *content* of a single backtick span for TTS.

    Rules (applied in priority order):
    1. If the content contains a path separator (/ or \\), reduce to basename.
    2. If the content contains underscores (snake_case), replace _ with space.
    3. Otherwise leave the word intact (CamelCase, simple token, etc.).

    The backtick characters themselves are always stripped by the caller.
    """
    # Rule 1: path → basename
    if "/" in content or "\\" in content:
        content = re.split(r"[/\\]", content)[-1]
    # Rule 2: snake_case → space-separated (applied to the (possibly
    # already-reduced) basename)
    if "_" in content:
        content = content.replace("_", " ")
    return content


def strip_urls(text: str) -> str:
    """Return *text* with URL-like tokens replaced for TTS-friendly reading.

    Processing order (each step feeds into the next):
    1. Backtick code-spans `` `token` `` → normalised plain text (R1).
    2. Markdown links ``[label](url)`` → label only.
    3. Bare URLs ``https://...`` / ``www.foo.com`` → ``[link]``.
    4. Bare file paths with separators → basename only.
    5. Long numeric tokens (7+ digits) → ``"a long number"`` (R2).

    Handles None / empty / non-str gracefully.
    """
    if not text:
        return text

    # R1: backtick code-spans — normalise content, strip backticks.
    def _replace_backtick(m: re.Match) -> str:
        return _normalize_backtick_span(m.group(1))

    text = _BACKTICK_SPAN.sub(_replace_backtick, text)

    # Order matters for the remaining steps: collapse markdown links first (so
    # their inner URL isn't matched separately by the URL pattern), then bare
    # URLs, then bare paths (so URL-internal path segments aren't
    # double-processed).
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _URL_PATTERN.sub("[link]", text)

    def _path_to_basename(m: re.Match) -> str:
        token = m.group(0)
        # Keep only the basename — last segment after / or \
        return re.split(r"[\\/]", token)[-1]

    text = _FILE_PATH.sub(_path_to_basename, text)

    # R2: long numeric tokens (7+ digits standalone) → "a long number".
    text = _LONG_NUMERIC.sub("a long number", text)

    return text


# IDE / Claude Code system-injected wrappers that shouldn't count as prose.
_SKIP_PROSE_PREFIXES = (
    "<ide_opened_file>", "<ide_selection>", "<local-command-caveat>",
    "<local-command-stdout>", "<local-command-stderr>", "<system-reminder>",
    "<system>", "<task-notification>", "<bash-input>", "<bash-stdout>",
    "<bash-stderr>", "<command-name>", "<command-args>", "<command-stdout>",
    "<command-stderr>", "<user-prompt-submit-hook>",
    "Base directory for this skill:", "Caveat: The messages below were generated",
)


def is_real_user_message(entry: dict) -> bool:
    """User entries with text content are real prompts; tool_result entries are not."""
    if entry.get("type") != "user":
        return False
    content = entry.get("message", {}).get("content", [])
    if isinstance(content, str):
        return bool(content)
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                return True
    return False


def collect_turn(transcript_path: str) -> tuple[list[str], list[dict], list | None]:
    """Walk transcript backward to the last real user message, then forward to
    collect this turn's assistant prose, tool_use entries, and the most recent
    TodoWrite todos array.

    Returns: (prose_entries, tool_uses, todos_or_None)
    """
    path = Path(transcript_path)
    if not path.exists():
        return [], [], None

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return [], [], None

    cutoff = 0
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except json.JSONDecodeError:
            continue
        if is_real_user_message(entry):
            cutoff = i + 1
            break

    prose_entries: list[str] = []
    tool_uses: list[dict] = []
    todos: list | None = None

    for i in range(cutoff, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            ct = c.get("type")
            if ct == "text" and c.get("text"):
                prose_entries.append(c["text"])
            elif ct == "tool_use":
                tool_uses.append(c)
                if c.get("name") == "TodoWrite":
                    todos = c.get("input", {}).get("todos", [])

    return prose_entries, tool_uses, todos


def recent_assistant_prose(
    session_id: str,
    catalog,  # SessionCatalog | None — or any object with entry_for/get returning path
    *,
    max_messages: int = 3,
    max_chars_per_message: int = 1500,
    max_age_seconds: float | None = None,
) -> list[str]:
    """Read the last N assistant prose messages from the session's transcript.

    Returns plain strings (no role prefix). Empty list when:
    - session_id is empty
    - catalog is None
    - catalog has no entry for this session
    - transcript file doesn't exist or is unreadable
    - no assistant messages in the recent window

    Each message is truncated to max_chars_per_message to bound prompt growth.

    2026-05-21 — added ``max_age_seconds`` to drop stale prose. The caller
    in modes/live.py was firing real-time narrations that re-quoted
    assistant prose from 30+ minutes prior as if it were current
    ("Still working through the audio stack — inspecting the Android
    ViewModel" when the agent had moved on to latency debugging an hour
    later). Set max_age_seconds to bound how far back the BACKGROUND
    CONTEXT can reach; when None, the old behavior (only max_messages
    bounds the window) applies.
    """
    if not session_id or catalog is None:
        return []

    # Support both SessionCatalog (entry_for) and test fakes (get).
    entry = None
    try:
        lookup = getattr(catalog, "entry_for", None) or getattr(catalog, "get", None)
        if lookup is not None:
            entry = lookup(session_id)
    except Exception as exc:
        logging.debug("recent_assistant_prose: catalog lookup failed: %s", exc)
        return []

    if entry is None:
        return []

    transcript_path = getattr(entry, "transcript_path", None)
    if not transcript_path:
        return []

    path = Path(transcript_path)
    if not path.exists():
        return []

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logging.debug("recent_assistant_prose: cannot read transcript: %s", exc)
        return []

    # Compute the staleness cutoff once, in epoch seconds. None = no filter.
    cutoff_epoch: float | None = None
    if max_age_seconds is not None and max_age_seconds > 0:
        import time as _time
        cutoff_epoch = _time.time() - float(max_age_seconds)

    collected: list[str] = []
    for raw in raw_lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("type") != "assistant":
            continue
        # 2026-05-21 — staleness gate. Drop entries older than the cutoff
        # so stale assistant prose can't bleed into fresh narrations.
        # The transcript stores ISO 8601 strings like "2026-05-22T05:46:13.194Z".
        # Best-effort: if parsing fails, keep the entry (don't silently
        # over-filter).
        if cutoff_epoch is not None:
            ts_raw = d.get("timestamp")
            if isinstance(ts_raw, str):
                try:
                    # datetime.fromisoformat handles "+00:00" but not "Z" pre-3.11.
                    from datetime import datetime
                    iso = ts_raw.replace("Z", "+00:00") if ts_raw.endswith("Z") else ts_raw
                    entry_epoch = datetime.fromisoformat(iso).timestamp()
                    if entry_epoch < cutoff_epoch:
                        continue
                except (ValueError, AttributeError):
                    pass
        content = d.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        # Concatenate all text blocks; skip tool_use blocks.
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text") or ""
                if text:
                    parts.append(text)
        if not parts:
            continue
        prose = "\n".join(parts).strip()
        if not prose:
            continue
        # Skip IDE-injected wrapper content.
        if any(prose.startswith(p) for p in _SKIP_PROSE_PREFIXES):
            continue
        # Strip URLs so the narrator doesn't read them aloud verbatim.
        prose = strip_urls(prose)
        # Truncate to bound prompt growth.
        if len(prose) > max_chars_per_message:
            prose = prose[:max_chars_per_message]
        collected.append(prose)

    # Return the LAST max_messages, oldest-first (most recent at end).
    return collected[-max_messages:]
