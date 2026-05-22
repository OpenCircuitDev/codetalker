"""Phase 26 — apply a Treatment to a Span, returning the replacement text or None to delete."""
from __future__ import annotations

from typing import Any

from .describer import (
    describe_code_fence,
    describe_currency_amount,
    describe_file_path,
    describe_ip_address,
    describe_iso_timestamp,
    describe_long_numeral,
    describe_subagent,
    describe_tool_output,
    read_currency_amount,
    read_ip_address,
    read_iso_timestamp,
)
from .forms import Treatment
from .recognizers import Span


def apply_treatment(span: Span, t: Treatment, cfg: dict[str, Any]) -> str | None:
    """Return replacement text for the span, or None to remove it entirely."""
    k = t.kind
    if k == "skip" or k == "log_silently":
        return None
    if k == "speak":
        return span.text  # passthrough; caller routes to TTS

    f = span.form
    if f == "code_fence":
        if k == "describe":
            return describe_code_fence(span.parsed.get("language", ""), span.parsed.get("line_count", 0))
        if k == "read":
            return span.text
    elif f == "inline_code":
        if k == "identifier_only":
            return span.text.strip("`") if span.parsed.get("is_identifier") else ""
        if k == "read":
            return span.text.strip("`")
    elif f == "todo_update":
        c = span.parsed.get("completed", 0)
        ip = span.parsed.get("in_progress", 0)
        p = span.parsed.get("pending", 0)
        if k == "count_only":
            return f"{c} done, {ip} in progress, {p} pending"
        if k == "itemize":
            limit = int((t.params or {}).get("max_items") or 5)
            todos = span.parsed.get("todos") or []
            items = []
            for todo in todos[:limit]:
                items.append(f"{todo.get('status', 'pending')}: {todo.get('content', '')}")
            return "; ".join(items)
        if k == "read":
            return ", ".join(td.get("content", "") for td in (span.parsed.get("todos") or []))
    elif f == "plan_block":
        body = (span.parsed.get("body") or "").strip()
        if k == "summarize":
            limit = int((t.params or {}).get("max_words") or 60)
            words = body.split()
            return " ".join(words[:limit]) + ("…" if len(words) > limit else "")
        if k == "read":
            return body
    elif f == "system_reminder":
        return None
    elif f == "tool_output":
        if k == "describe":
            return describe_tool_output(
                span.parsed.get("tool_name", ""),
                span.parsed.get("exit_code"),
                span.parsed.get("line_count", 0),
            )
        if k == "read":
            return span.text
    elif f == "subagent_dispatch":
        phase = span.parsed.get("phase", "pre")
        st = span.parsed.get("subagent_type")
        if k == "announce":
            return f"dispatching {st or 'subagent'}" if phase == "pre" else ""
        if k == "describe":
            return describe_subagent(phase, st)
    elif f == "file_path":
        path = span.parsed.get("path") or span.text
        if k == "filename":
            return describe_file_path(path, "filename")
        if k == "describe":
            return describe_file_path(path, "describe")
        if k == "read":
            return path
    elif f == "long_numeral":
        if k == "describe":
            return describe_long_numeral(span.text)
        if k == "read":
            return span.text
    elif f == "ip_address":
        host = span.parsed.get("host", "")
        port = span.parsed.get("port")
        if k == "describe":
            return describe_ip_address(host, port)
        if k == "read":
            return read_ip_address(host, port)
    elif f == "iso_timestamp":
        raw = span.parsed.get("raw", "")
        if k == "describe":
            return describe_iso_timestamp()
        if k == "read":
            return read_iso_timestamp(raw)
    elif f == "currency_amount":
        raw = span.parsed.get("raw", "")
        if k == "describe":
            return describe_currency_amount()
        if k == "read":
            return read_currency_amount(raw)
    elif f == "audible_block":
        return span.text  # passthrough; trigger parser owns dispatch

    return None
