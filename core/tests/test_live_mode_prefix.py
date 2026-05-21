"""Tests for LiveMode prompt prefix stability (Sub-task 1.2).

Verifies that the static portion of the narration prompt (system instructions +
optional teacher directives) is byte-identical across cadence calls that share
the same teacher_cfg but differ in their events lists. This enables Google
Gemini's implicit prompt prefix caching (>=1024-token shared prefix).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from claude_code_talker.modes.live import LiveMode, LIVE_NARRATION_SYSTEM, _EVENTS_HEADER
from claude_code_talker.event_buffer import EventBuffer, Event
from claude_code_talker.cadence.periodic import PeriodicCadence


def _make_mode(cfg=None, sessions=None):
    buf = EventBuffer()
    cadence = PeriodicCadence(period_seconds=10.0)
    return LiveMode(
        provider=None,
        cadence=cadence,
        event_buffer=buf,
        audio_queue=MagicMock(),
        cfg=cfg or {},
        sessions=sessions,
    )


def _event(ts=0.0, ev_type="POST_TOOL", tool="Read"):
    return Event(
        timestamp=ts,
        type=ev_type,
        metadata={"tool_name": tool, "success": True},
        significance=0.3,
    )


def _static_prefix(prompt: str) -> str:
    """Extract everything before the events block marker.

    2026-05-17 — marker renamed from "RECENT EVENTS" to "CURRENT EVENTS"
    when the interpreter-style prompt rewrite started tagging the focus
    + reasoning blocks as BACKGROUND CONTEXT. The contrast with
    "CURRENT EVENTS" is the whole point of the new tagging.
    """
    marker = "CURRENT EVENTS"
    idx = prompt.index(marker)
    return prompt[:idx]


# ---------------------------------------------------------------------------
# No teacher mode: prefix is byte-identical for two different event lists
# ---------------------------------------------------------------------------

def test_prefix_identical_no_teacher_different_events():
    mode_a = _make_mode(cfg={})
    mode_b = _make_mode(cfg={})

    events_a = [_event(ts=0.0, ev_type="PRE_TOOL", tool="Bash")]
    events_b = [
        _event(ts=0.0, ev_type="POST_TOOL", tool="Read"),
        _event(ts=2.0, ev_type="PROSE", tool="Edit"),
    ]

    prefix_a = _static_prefix(mode_a._build_prompt(events_a))
    prefix_b = _static_prefix(mode_b._build_prompt(events_b))

    assert prefix_a == prefix_b


# ---------------------------------------------------------------------------
# With teacher mode on: prefix still identical (teacher block is static)
# ---------------------------------------------------------------------------

def test_prefix_identical_with_teacher_mode_different_events():
    teacher_cfg = {
        "enabled": True,
        "depth_level": 3,
        "verbosity": "standard",
        "granularity": "combined",
        "substitution": False,
        "glossary": False,
        "reframe": False,
    }
    cfg = {"teacher_mode": teacher_cfg}

    mode_a = _make_mode(cfg=cfg)
    mode_b = _make_mode(cfg=cfg)

    events_a = [_event(ts=0.0, ev_type="PRE_TOOL", tool="Write")]
    events_b = [
        _event(ts=0.0, ev_type="PRE_TOOL", tool="Bash"),
        _event(ts=1.0, ev_type="POST_TOOL", tool="Bash"),
        _event(ts=2.5, ev_type="USER_PROMPT", tool=""),
    ]

    prefix_a = _static_prefix(mode_a._build_prompt(events_a))
    prefix_b = _static_prefix(mode_b._build_prompt(events_b))

    assert prefix_a == prefix_b


# ---------------------------------------------------------------------------
# Events list is placed AFTER the static prefix (separator is last static part)
# ---------------------------------------------------------------------------

def test_events_header_comes_after_system_text():
    mode = _make_mode()
    events = [_event()]
    prompt = mode._build_prompt(events)

    # 2026-05-21 — system prompt rewritten for briefness. The earlier
    # "INTERPRETER for the user" anchor disappeared when the prompt was
    # tightened. The new anchor is "BRIEFNESS IS PRIMARY" — the directive
    # that drives the whole rewrite. The test still proves the same
    # thing: system instructions come before the events block.
    system_idx = prompt.index("BRIEFNESS IS PRIMARY")
    events_idx = prompt.index("CURRENT EVENTS")

    assert system_idx < events_idx, (
        "System instructions must appear before CURRENT EVENTS marker"
    )


# ---------------------------------------------------------------------------
# Teacher directives appear BEFORE the events, not after
# ---------------------------------------------------------------------------

def test_teacher_directives_before_events():
    teacher_cfg = {"enabled": True, "depth_level": 4, "verbosity": "expanded"}
    mode = _make_mode(cfg={"teacher_mode": teacher_cfg})
    events = [_event()]
    prompt = mode._build_prompt(events)

    teacher_idx = prompt.index("TEACHER MODE")
    events_idx = prompt.index("CURRENT EVENTS")

    assert teacher_idx < events_idx, (
        "Teacher directives must appear before RECENT EVENTS marker "
        "so the static prefix (system + teacher) is maximally cacheable"
    )


# ---------------------------------------------------------------------------
# Different teacher_cfgs produce different prefixes (sanity check)
# ---------------------------------------------------------------------------

def test_different_teacher_cfgs_produce_different_prefixes():
    cfg_a = {"teacher_mode": {"enabled": True, "depth_level": 1, "verbosity": "concise"}}
    cfg_b = {"teacher_mode": {"enabled": True, "depth_level": 5, "verbosity": "expanded"}}

    mode_a = _make_mode(cfg=cfg_a)
    mode_b = _make_mode(cfg=cfg_b)

    events = [_event()]
    prefix_a = _static_prefix(mode_a._build_prompt(events))
    prefix_b = _static_prefix(mode_b._build_prompt(events))

    assert prefix_a != prefix_b, (
        "Different teacher configs should produce different prefixes"
    )
