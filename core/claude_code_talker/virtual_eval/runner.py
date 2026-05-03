"""Sample selection + batch eval execution for virtual user evaluation."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from claude_code_talker.narration_log import NarrationLog


# Modes worth evaluating (excludes test/diagnostic modes that aren't user-facing).
DEFAULT_INCLUDED_MODES = ("live", "live-stream", "brief", "prompt-brief", "chat")


@dataclass
class EvalRequest:
    """Parameters controlling a single virtual-eval run."""
    max_narrations: int = 50
    deployed_at: float = 0.0  # only narrations with timestamp >= this are eligible
    included_modes: tuple[str, ...] = DEFAULT_INCLUDED_MODES
    seed: int | None = None  # for deterministic sampling in tests


def select_narration_sample(log: NarrationLog, request: EvalRequest) -> list[dict]:
    """Read all narration entries; filter by mode + deployed_at; stratified-cap.

    Returns a list of plain dicts (the same shape `NarrationLog.tail()` returns).
    Stratified sampling means each included mode contributes proportional entries
    when the eligible set exceeds ``max_narrations`` — preserves mode diversity.
    """
    # Read everything (NarrationLog.tail with a huge limit captures all)
    all_entries = log.tail(n=10_000)
    eligible = [
        e for e in all_entries
        if e.get("mode") in request.included_modes
        and float(e.get("timestamp", 0)) >= request.deployed_at
    ]
    if not eligible:
        return []
    if len(eligible) <= request.max_narrations:
        return eligible
    # Stratified sample: split by mode, sample proportional to mode-share
    by_mode: dict[str, list[dict]] = {}
    for e in eligible:
        by_mode.setdefault(e["mode"], []).append(e)
    rng = random.Random(request.seed)
    per_mode = max(1, request.max_narrations // len(by_mode))
    sampled: list[dict] = []
    for mode, entries in by_mode.items():
        if len(entries) <= per_mode:
            sampled.extend(entries)
        else:
            sampled.extend(rng.sample(entries, per_mode))
    # If we under-shot the cap (small modes), top up with random eligible
    if len(sampled) < request.max_narrations:
        remaining = [e for e in eligible if e not in sampled]
        deficit = request.max_narrations - len(sampled)
        if remaining and deficit > 0:
            sampled.extend(rng.sample(remaining, min(deficit, len(remaining))))
    return sampled[:request.max_narrations]
