"""Gather full session context for each narration before scoring it.

A persona can't accurately judge a narration in isolation — they need to know
what was happening in the session. This module pulls (a) prior narrations
from the same session, (b) the user's most recent prompt, and (c) a few
recent transcript turns into a NarrationWithContext that the runner sends to
the LLM together with the narration being scored.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from claude_code_talker.narration_log import NarrationLog


@dataclass
class NarrationWithContext:
    """A narration plus the surrounding session state at the time it fired."""
    text: str
    session_id: str
    timestamp: float
    mode: str = ""
    prior_narrations: list[str] = field(default_factory=list)
    last_user_prompt: str = ""
    recent_transcript_lines: list[str] = field(default_factory=list)


def _read_transcript_for_context(
    transcript_path: Path,
    *,
    max_lines: int = 10,
) -> tuple[str, list[str]]:
    """Best-effort: read the last N user/assistant turns from a transcript.

    Returns (last_user_prompt, list_of_rendered_lines).
    Skips IDE-injected wrappers (same logic as chat_panel.gather_session_context).
    """
    if not transcript_path or not transcript_path.exists():
        return "", []
    try:
        raw_lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", []
    rendered: list[str] = []
    last_user = ""
    skip_prefixes = (
        "<ide_opened_file>", "<ide_selection>", "<local-command-caveat>",
        "<local-command-stdout>", "<local-command-stderr>", "<system-reminder>",
        "<system>", "<task-notification>", "<bash-input>", "<bash-stdout>",
        "Base directory for this skill:", "Caveat: The messages below were generated",
    )
    for raw in raw_lines[-max_lines * 4:]:
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
            if not text or any(text.startswith(p) for p in skip_prefixes):
                continue
            rendered.append(f"USER: {text[:300]}")
            last_user = text  # latest user message wins
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
                rendered.append(f"ASSISTANT: {text[:300]}")
    return last_user, rendered[-max_lines:]


def gather_context_for_narration(
    target: dict,
    narration_log: NarrationLog,
    catalog,  # SessionCatalog | None
    *,
    max_prior_narrations: int = 8,
    max_transcript_lines: int = 10,
) -> NarrationWithContext:
    """Build a NarrationWithContext for a single sampled narration.

    Args:
        target: a dict shaped like NarrationLog entries (must have session_id +
            text + timestamp).
        narration_log: live NarrationLog to scan for prior entries.
        catalog: SessionCatalog or None. If None, transcript context is omitted.

    Returns the populated NarrationWithContext.
    """
    target_sid = target.get("session_id", "")
    target_ts = float(target.get("timestamp", 0.0))
    target_text = target.get("text", "")
    # Prior narrations from same session, strictly older than target
    all_entries = narration_log.tail(n=10_000)
    prior = [
        e for e in all_entries
        if e.get("session_id") == target_sid
        and float(e.get("timestamp", 0.0)) < target_ts
    ]
    prior.sort(key=lambda e: float(e.get("timestamp", 0.0)))
    prior_texts = [
        f"[{e.get('mode', '?')}] {(e.get('text') or '')[:200]}"
        for e in prior[-max_prior_narrations:]
    ]
    # Transcript context if catalog has the session
    last_user = ""
    transcript_lines: list[str] = []
    if catalog is not None and target_sid:
        try:
            entry = catalog.entry_for(target_sid)
        except Exception:
            entry = None
        if entry is not None and entry.transcript_path:
            last_user, transcript_lines = _read_transcript_for_context(
                entry.transcript_path, max_lines=max_transcript_lines,
            )
    return NarrationWithContext(
        text=target_text,
        session_id=target_sid,
        timestamp=target_ts,
        mode=target.get("mode", ""),
        prior_narrations=prior_texts,
        last_user_prompt=last_user,
        recent_transcript_lines=transcript_lines,
    )
