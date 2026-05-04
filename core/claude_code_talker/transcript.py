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


def strip_urls(text: str) -> str:
    """Return *text* with every URL replaced by the literal string '[link]'.

    Used to keep TTS from reading aloud arbitrary URLs in assistant prose,
    user prompts, or tool output snippets.  Handles None / empty / non-str
    gracefully.
    """
    if not text:
        return text
    return _URL_PATTERN.sub("[link]", text)


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
) -> list[str]:
    """Read the last N assistant prose messages from the session's transcript.

    Returns plain strings (no role prefix). Empty list when:
    - session_id is empty
    - catalog is None
    - catalog has no entry for this session
    - transcript file doesn't exist or is unreadable
    - no assistant messages in the recent window

    Each message is truncated to max_chars_per_message to bound prompt growth.
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
