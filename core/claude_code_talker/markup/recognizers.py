"""Phase 26 — recognizers for the ten markup forms."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Span:
    form: str
    start: int
    end: int
    text: str
    parsed: dict[str, Any] = field(default_factory=dict)


_RE_CODE_FENCE = re.compile(r"^```([^\n]*)\n([\s\S]*?)\n```", re.MULTILINE)
_RE_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_RE_IDENTIFIER = re.compile(r"^[A-Za-z_][\w.]*$")
_RE_SYSTEM_REMINDER = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")
_RE_FILE_PATH = re.compile(
    r"`?([\w./\\-]+\.[A-Za-z0-9]{1,8})(?::\d+)?`?"
)
_RE_LONG_NUMERAL = re.compile(r"\b\d{7,}\b")
_RE_PLAN_HEADER = re.compile(r"^##\s+Plan\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)
_RE_AUDIBLE_HEADER = re.compile(
    r"^##\s+Audible\s+([A-Za-z][\w-]*)\s*\n([\s\S]*?)(?=\n##\s|\Z)",
    re.MULTILINE,
)


def detect_code_fence(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_CODE_FENCE.finditer(text):
        lang = (m.group(1) or "").strip()
        body = m.group(2) or ""
        out.append(Span(
            form="code_fence",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"language": lang, "line_count": body.count("\n") + (0 if not body else 1)},
        ))
    return out


def detect_inline_code(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_INLINE_CODE.finditer(text):
        body = m.group(1)
        out.append(Span(
            form="inline_code",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"is_identifier": bool(_RE_IDENTIFIER.match(body))},
        ))
    return out


def detect_system_reminder(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_SYSTEM_REMINDER.finditer(text):
        out.append(Span("system_reminder", m.start(), m.end(), m.group(0)))
    return out


def detect_file_path(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_FILE_PATH.finditer(text):
        path = m.group(1)
        if "/" not in path and "\\" not in path:
            continue  # require a directory separator to avoid false positives like "x.y"
        # Skip URL-like matches (the URL handler in modes/direct.py rewrites them).
        prefix = text[max(0, m.start() - 3):m.start()]
        if prefix.endswith("://") or prefix.endswith(":/"):
            continue
        # Skip leading-slash UNC-style fragments produced by greedy matching
        # against http://host/path — basename() returns empty for these and
        # the legacy URL handler will pick them up.
        if path.startswith("//") or path.startswith("\\\\"):
            continue
        out.append(Span(
            form="file_path",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"path": path},
        ))
    return out


def detect_long_numeral(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_LONG_NUMERAL.finditer(text):
        out.append(Span("long_numeral", m.start(), m.end(), m.group(0)))
    return out


def detect_plan_block(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_PLAN_HEADER.finditer(text):
        out.append(Span(
            form="plan_block",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"body": m.group(1)},
        ))
    return out


def detect_audible_block(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_AUDIBLE_HEADER.finditer(text):
        out.append(Span(
            form="audible_block",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"tag": m.group(1).lower(), "body": m.group(2)},
        ))
    return out


def detect_todo_update(event: dict[str, Any]) -> list[Span]:
    if event.get("kind") != "tool_use" or event.get("name") != "TodoWrite":
        return []
    todos = (event.get("input") or {}).get("todos") or []
    counts = {"completed": 0, "in_progress": 0, "pending": 0}
    for t in todos:
        s = (t or {}).get("status") or "pending"
        counts[s] = counts.get(s, 0) + 1
    return [Span(
        form="todo_update",
        start=0, end=0, text="",
        parsed={"todos": todos, **counts},
    )]


def detect_tool_output(event: dict[str, Any]) -> list[Span]:
    if event.get("kind") != "post_tool":
        return []
    name = event.get("name") or ""
    if name == "Task":
        return []  # handled by detect_subagent_dispatch
    stdout = event.get("stdout") or ""
    return [Span(
        form="tool_output",
        start=0, end=0, text=stdout,
        parsed={
            "tool_name": name,
            "exit_code": event.get("exit_code"),
            "line_count": stdout.count("\n"),
        },
    )]


def detect_subagent_dispatch(event: dict[str, Any]) -> list[Span]:
    name = event.get("name") or ""
    kind = event.get("kind") or ""
    if name != "Task":
        return []
    phase = "pre" if kind == "tool_use" else "post" if kind == "post_tool" else None
    if phase is None:
        return []
    parsed: dict[str, Any] = {"phase": phase, "tool_use_id": event.get("id")}
    if phase == "pre":
        parsed["subagent_type"] = (event.get("input") or {}).get("subagent_type")
    return [Span("subagent_dispatch", 0, 0, "", parsed=parsed)]
