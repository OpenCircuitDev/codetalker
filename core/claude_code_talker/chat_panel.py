"""Phase 9: chat panel — let the user ask the LLM questions about a session.

Gathers session context (recent events from the buffer + recent transcript
lines) and sends a chat-style prompt to the configured LLM provider. Honors
teacher_mode if enabled. The same provider stack the narration uses also serves
chat — typically the cost-effective default (e.g. google/gemini-2.0-flash-001
via OpenRouter).

Returned response is plain text suitable for either UI rendering or TTS
narration.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from claude_code_talker.teacher_mode import merge_teacher_into_prompt


CHAT_PROMPT_TEMPLATE = """\
You are an analyst helping the user understand a Claude Code session they own.
Answer their question using ONLY the session context below. Be concise and
accurate. If the context doesn't cover the answer, say so plainly. Use 1-3
short paragraphs of plain English suitable for spoken narration.

SESSION CONTEXT (most recent last):
{context}

USER QUESTION:
{question}

ANSWER:"""


def _last_n_transcript_lines(transcript_path: Path, n_lines: int) -> list[str]:
    """Read the last ``n_lines`` JSONL records from a transcript and render a
    one-line text summary for each. Skips system-injected wrappers."""
    if not transcript_path or not transcript_path.exists():
        return []
    try:
        raw_lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[str] = []
    for raw in raw_lines[-n_lines * 4:]:  # over-read; we filter
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        t = d.get("type")
        if t == "user":
            msg = d.get("message")
            text = ""
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list) and content:
                    head = content[0]
                    if isinstance(head, dict):
                        text = head.get("text") or ""
            text = text.strip()
            # Skip IDE/system tags + skill loader preface
            stripped = text.lstrip()
            if (stripped.startswith("<") or
                    stripped.startswith("Base directory for this skill:") or
                    stripped.startswith("Caveat: The messages below were generated")):
                continue
            if not text:
                continue
            out.append(f"USER: {text[:300]}")
        elif t == "assistant":
            msg = d.get("message")
            text = ""
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = []
                    for p in content:
                        if isinstance(p, dict) and p.get("type") == "text":
                            parts.append(p.get("text") or "")
                    text = "\n".join(parts)
            text = text.strip()
            if text:
                out.append(f"ASSISTANT: {text[:300]}")
        elif t == "ai-title":
            title = d.get("aiTitle")
            if isinstance(title, str) and title:
                out.append(f"[SESSION TITLE: {title}]")
    return out[-n_lines:]


def _format_events(events: Iterable, max_events: int = 20) -> list[str]:
    """Render recent EventBuffer events as one line each."""
    out: list[str] = []
    events_list = list(events)
    if not events_list:
        return out
    t0 = events_list[0].timestamp
    for ev in events_list[-max_events:]:
        dt = ev.timestamp - t0
        meta = ev.metadata
        if ev.type == "PRE_TOOL":
            out.append(f"[T+{dt:.1f}s tool→ {meta.get('tool_name', '?')}]")
        elif ev.type == "POST_TOOL":
            ok = "ok" if meta.get("success", True) else "FAILED"
            out.append(f"[T+{dt:.1f}s tool← {meta.get('tool_name', '?')} {ok}]")
        elif ev.type == "NOTIFICATION":
            out.append(f"[T+{dt:.1f}s notif] {meta.get('message', '')[:100]}")
        elif ev.type == "PROSE":
            out.append(f"[T+{dt:.1f}s prose] {(meta.get('text') or '')[:100]}")
    return out


def gather_session_context(
    *,
    transcript_path: Path | None,
    events: Iterable,
    transcript_lines: int = 25,
    event_count: int = 20,
) -> str:
    """Compose a context block for the LLM from disk transcript + live event buffer."""
    parts: list[str] = []
    transcript_part = _last_n_transcript_lines(transcript_path, transcript_lines) if transcript_path else []
    event_part = _format_events(events, event_count)
    if transcript_part:
        parts.append("--- Recent transcript ---")
        parts.extend(transcript_part)
    if event_part:
        parts.append("--- Recent live events ---")
        parts.extend(event_part)
    if not parts:
        parts.append("(no context available)")
    return "\n".join(parts)


async def answer_question(
    *,
    question: str,
    context: str,
    provider,
    teacher_cfg: dict | None,
    max_tokens: int = 400,
) -> str:
    """Send the chat prompt to ``provider`` and return its response.

    Honors teacher_mode by appending directives to the base prompt.
    """
    base = CHAT_PROMPT_TEMPLATE.format(context=context, question=question)
    prompt = merge_teacher_into_prompt(base, teacher_cfg)
    try:
        text = await provider.complete(prompt, max_tokens=max_tokens)
    except Exception as e:
        logging.warning("chat panel provider failed: %s", e)
        return f"(provider error: {e})"
    return (text or "").strip()
