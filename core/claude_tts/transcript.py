"""Parse Claude Code's JSONL transcript files into per-turn structures."""
from __future__ import annotations

import json
from pathlib import Path


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
