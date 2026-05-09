"""Phase 26 — markup form catalog, Treatment dataclass, mode presets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Treatment:
    kind: str
    params: dict = field(default_factory=dict)


FORM_KINDS: dict[str, set[str]] = {
    "code_fence":         {"skip", "describe", "read"},
    "inline_code":        {"skip", "identifier_only", "read"},
    "todo_update":        {"skip", "count_only", "itemize", "read"},
    "plan_block":         {"skip", "summarize", "read"},
    "audible_block":      {"speak"},
    "system_reminder":    {"skip", "log_silently"},
    "tool_output":        {"skip", "describe", "read"},
    "subagent_dispatch":  {"skip", "announce", "describe"},
    "file_path":          {"skip", "filename", "describe", "read"},
    "long_numeral":       {"skip", "describe", "read"},
}


PRESETS: dict[str, dict[str, Treatment]] = {
    "brief": {
        "code_fence":        Treatment("skip"),
        "inline_code":       Treatment("identifier_only"),
        "todo_update":       Treatment("count_only"),
        "plan_block":        Treatment("summarize", {"max_words": 60}),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("describe"),
        "subagent_dispatch": Treatment("announce"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
    "direct": {
        "code_fence":        Treatment("describe"),
        "inline_code":       Treatment("read"),
        "todo_update":       Treatment("itemize", {"max_items": 5}),
        "plan_block":        Treatment("read"),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("read"),
        "subagent_dispatch": Treatment("describe"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
    "live": {
        "code_fence":        Treatment("describe"),
        "inline_code":       Treatment("identifier_only"),
        "todo_update":       Treatment("itemize", {"max_items": 3}),
        "plan_block":        Treatment("summarize", {"max_words": 80}),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("describe"),
        "subagent_dispatch": Treatment("describe"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
    "trigger": {
        "code_fence":        Treatment("skip"),
        "inline_code":       Treatment("identifier_only"),
        "todo_update":       Treatment("skip"),
        "plan_block":        Treatment("skip"),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("skip"),
        "subagent_dispatch": Treatment("skip"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
}


def validate_treatment(form: str, t: Treatment) -> None:
    if form not in FORM_KINDS:
        raise ValueError(f"unknown form: {form}")
    if t.kind not in FORM_KINDS[form]:
        raise ValueError(f"kind {t.kind!r} not allowed for {form}")


def preset_for_mode(mode: str) -> dict[str, Treatment]:
    return PRESETS.get(mode, PRESETS["direct"])


def load_treatments(cfg: dict[str, Any]) -> dict[str, Treatment]:
    mode = (cfg.get("mode") or "direct").lower()
    base = dict(preset_for_mode(mode))
    user = (cfg.get("markup") or {})
    for form in FORM_KINDS:
        node = user.get(form)
        if not isinstance(node, dict):
            continue
        kind = node.get("kind")
        if kind is None:
            continue
        params = node.get("params") or {}
        candidate = Treatment(kind=str(kind), params=dict(params))
        try:
            validate_treatment(form, candidate)
        except ValueError:
            continue  # silently fall back to preset
        base[form] = candidate
    return base
