"""Phase 26 — single-entry transform for prose + event streams."""
from __future__ import annotations

import re
from typing import Any

from .forms import Treatment, load_treatments
from .recognizers import (
    Span,
    detect_audible_block,
    detect_code_fence,
    detect_file_path,
    detect_inline_code,
    detect_long_numeral,
    detect_plan_block,
    detect_subagent_dispatch,
    detect_system_reminder,
    detect_todo_update,
    detect_tool_output,
)
from .treatment import apply_treatment


_BLOCK_DETECTORS = (
    ("system_reminder", detect_system_reminder),
    ("code_fence", detect_code_fence),
    ("plan_block", detect_plan_block),
)
_SPAN_DETECTORS = (
    ("inline_code", detect_inline_code),
    ("file_path", detect_file_path),
    ("long_numeral", detect_long_numeral),
)


def _replace(text: str, spans: list[tuple[Span, str | None]]) -> str:
    if not spans:
        return text
    spans = sorted(spans, key=lambda x: x[0].start, reverse=True)
    out = text
    for span, replacement in spans:
        out = out[:span.start] + (replacement if replacement is not None else "") + out[span.end:]
    return out


def _audible_passthrough(text: str) -> tuple[str, list[tuple[int, str]]]:
    """Pull audible blocks out of *text*, returning text-with-placeholders + list of (idx, original).

    The placeholder token (``\x00AUDIBLE{i}\x00``) survives downstream regex
    transforms unchanged because it contains no markup-significant characters.
    """
    blocks = detect_audible_block(text)
    if not blocks:
        return text, []
    holes: list[tuple[int, str]] = []
    out = text
    # Replace from the end of the string back to the start so earlier offsets
    # remain valid as we go.
    for i, b in enumerate(reversed(blocks)):
        # `i` here counts in reverse; we want stable indexing tied to the
        # original block order, so flip back.
        idx = len(blocks) - 1 - i
        token = f"\x00AUDIBLE{idx}\x00"
        out = out[:b.start] + token + out[b.end:]
        holes.append((idx, b.text))
    # Sort so caller can scan in increasing index order
    holes.sort(key=lambda h: h[0])
    return out, holes


def _restore_audible(text: str, holes: list[tuple[int, str]]) -> str:
    for idx, original in holes:
        text = text.replace(f"\x00AUDIBLE{idx}\x00", original)
    return text


def transform(prose: str, cfg: dict[str, Any]) -> str:
    if not prose:
        return prose
    treatments = load_treatments(cfg)

    masked, holes = _audible_passthrough(prose)

    block_spans: list[tuple[Span, str | None]] = []
    for form, detector in _BLOCK_DETECTORS:
        for span in detector(masked):
            replacement = apply_treatment(span, treatments[form], cfg)
            block_spans.append((span, replacement))
    out = _replace(masked, block_spans)

    span_replacements: list[tuple[Span, str | None]] = []
    for form, detector in _SPAN_DETECTORS:
        for span in detector(out):
            replacement = apply_treatment(span, treatments[form], cfg)
            span_replacements.append((span, replacement))
    out = _replace(out, span_replacements)

    out = _restore_audible(out, holes)

    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out


def transform_event(event: dict[str, Any], cfg: dict[str, Any]) -> str | None:
    treatments = load_treatments(cfg)
    if event.get("name") == "TodoWrite" and event.get("kind") == "tool_use":
        spans = detect_todo_update(event)
        if spans:
            return apply_treatment(spans[0], treatments["todo_update"], cfg)
    if event.get("name") == "Task":
        spans = detect_subagent_dispatch(event)
        if spans:
            return apply_treatment(spans[0], treatments["subagent_dispatch"], cfg)
    if event.get("kind") == "post_tool":
        spans = detect_tool_output(event)
        if spans:
            return apply_treatment(spans[0], treatments["tool_output"], cfg)
    return None


def transform_for_live(prose: str, cfg: dict[str, Any], tag_overrides: dict | None = None) -> str:
    """Live-mode entry point. Optionally layer per-tag *markup_overrides* on top
    of the active session cfg before running the standard ``transform`` pipeline.

    *tag_overrides* must be the dict directly off ``Tag.markup_overrides``,
    keyed by form name (e.g. ``{"plan_block": {"kind": "read"}}``).
    """
    if tag_overrides:
        markup = dict(cfg.get("markup") or {})
        for form, override in (tag_overrides or {}).items():
            existing = dict(markup.get(form) or {})
            if isinstance(override, dict):
                existing.update(override)
            markup[form] = existing
        cfg = {**cfg, "markup": markup}
    return transform(prose, cfg)
