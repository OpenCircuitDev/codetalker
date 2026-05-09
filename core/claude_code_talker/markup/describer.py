"""Phase 26 — human-language renderers for markup spans."""
from __future__ import annotations

import os


def describe_code_fence(language: str, line_count: int) -> str:
    if line_count <= 1:
        size = "a one-line"
    elif line_count < 10:
        size = "a short"
    elif line_count < 50:
        size = "a medium"
    else:
        size = "a long"
    lang = f"{language} " if language else ""
    return f"{size} {lang}code block of about {line_count} lines"


def describe_long_numeral(_text: str) -> str:
    return "a long number"


def describe_file_path(path: str, mode: str = "filename") -> str:
    base = os.path.basename(path.split(":", 1)[0])
    if mode == "filename":
        return base
    return f"the file {base}"


def describe_tool_output(tool: str, exit_code: int | None, line_count: int) -> str:
    state = "succeeded" if exit_code == 0 else f"exited with code {exit_code}" if exit_code else "ran"
    return f"{tool} {state} with {line_count} lines of output"


def describe_subagent(phase: str, subagent_type: str | None) -> str:
    label = subagent_type or "subagent"
    if phase == "pre":
        return f"dispatching {label}"
    return f"{label} returned"
