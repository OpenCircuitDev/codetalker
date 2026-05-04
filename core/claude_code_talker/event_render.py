"""Render tool input/response metadata into compact prompt-friendly strings.

Pure helpers — no I/O, no side effects, no mutable defaults.
Used by live.py _build_prompt (and any other mode that renders PRE_TOOL /
POST_TOOL events in a narrator prompt) to surface file paths, commands, and
outcomes rather than bare tool names.
"""
from __future__ import annotations

import ast
import re
from os.path import basename

from claude_code_talker.transcript import strip_urls


_FILE_PATH_TOOLS = {"Edit", "Write", "Read", "NotebookEdit", "MultiEdit"}
_PATTERN_TOOLS = {"Glob", "Grep"}


def _safe_parse_dict(raw: str) -> dict | None:
    """Parse the str(dict) representation captured at ingest. Returns None on failure."""
    raw = (raw or "").strip()
    if not raw or not raw.startswith("{"):
        return None
    try:
        v = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    return v if isinstance(v, dict) else None


def summarize_tool_input(tool_name: str, raw_input: str) -> str:
    """Compact one-line summary of a tool's input metadata for narrator prompt.

    Args:
        tool_name: The name of the tool (e.g. "Edit", "Bash", "Grep").
        raw_input: The str(dict) captured at ingest (metadata["input"]).

    Returns:
        A short human-readable string (≤80 chars). Empty string if raw_input
        is empty.
    """
    if not raw_input:
        return ""
    d = _safe_parse_dict(raw_input)
    if d is None:
        # Fallback: truncate the raw string
        return raw_input[:80]
    if tool_name in _FILE_PATH_TOOLS:
        fp = d.get("file_path") or d.get("notebook_path") or ""
        return basename(str(fp))[:80] if fp else str(d)[:80]
    if tool_name == "Bash":
        cmd = str(d.get("command", ""))
        return strip_urls(cmd)[:80]
    if tool_name in _PATTERN_TOOLS:
        pat = str(d.get("pattern", ""))
        path = str(d.get("path", ""))
        if path:
            return f"{pat} in {basename(path)}"[:80]
        return pat[:80]
    if tool_name == "TodoWrite":
        todos = d.get("todos", []) or []
        in_prog = sum(
            1 for t in todos
            if isinstance(t, dict) and t.get("status") == "in_progress"
        )
        return f"{in_prog} in_progress" if in_prog else f"{len(todos)} todos"
    if tool_name == "WebFetch":
        raw_url = str(d.get("url", ""))
        # Show domain only so narrator says something meaningful without
        # reciting the full path (e.g. "github.com" not the full blob URL).
        m = re.match(r"https?://([^/\s]+)", raw_url, re.IGNORECASE)
        return f"[{m.group(1)}]" if m else "[link]"
    if tool_name == "WebSearch":
        return str(d.get("query", ""))[:80]
    # Default: stringified dict, truncated
    return strip_urls(str(d))[:80]


_BASH_STDOUT_CAP = 200

# Pattern sets for Bash output signal detection (matched case-insensitively).
_PASS_PATTERNS = ("passed", "tests passed", "built successfully", "compilation finished", "ok")
_FAIL_PATTERNS = ("failed", "error:", "traceback", "exception:")


def _bash_signal_prefix(text_lower: str) -> str:
    """Return '✓ ', '✗ ', or '' based on signal patterns in lowercased stdout."""
    for pat in _PASS_PATTERNS:
        if pat in text_lower:
            return "✓ "
    for pat in _FAIL_PATTERNS:
        if pat in text_lower:
            return "✗ "
    return ""


def summarize_tool_response(tool_name: str, raw_response: str, success: bool) -> str:
    """Compact one-line summary of a tool's response metadata.

    Args:
        tool_name: The name of the tool (e.g. "Bash", "Edit").
        raw_response: The str(dict) captured at ingest (metadata["response"]).
        success: Whether the tool call succeeded.

    Returns:
        A short human-readable string. Never raises.
    """
    d = _safe_parse_dict(raw_response) if raw_response else None
    if not success:
        if tool_name == "Bash" and d:
            exit_code = d.get("exit_code")
            stdout = strip_urls(str(d.get("stdout") or d.get("output") or ""))[:_BASH_STDOUT_CAP]
            if exit_code is not None:
                text = stdout if stdout else str(d.get("error") or d.get("message") or "")[:80]
                return f"(exit {exit_code}) {text}" if text else f"(exit {exit_code})"
            err = str(d.get("error") or d.get("message") or "")[:80]
            return f"FAILED: {err}" if err else "FAILED"
        if d:
            err = str(d.get("error") or d.get("message") or "")[:80]
            return f"FAILED: {err}" if err else "FAILED"
        return f"FAILED: {(raw_response or '')[:80]}" if raw_response else "FAILED"
    if tool_name == "Bash" and d:
        out = strip_urls(str(d.get("stdout") or d.get("output") or ""))[:_BASH_STDOUT_CAP]
        if out:
            prefix = _bash_signal_prefix(out.lower())
            return f"{prefix}{out}"
    # Edit / Write / Read / etc. — bare "ok" is fine
    return "ok"
