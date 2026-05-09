"""Phase 26 — pipeline assembly tests."""
from __future__ import annotations

from claude_code_talker.markup.pipeline import transform, transform_event


def test_transform_strips_code_fence_in_brief_mode():
    cfg = {"mode": "brief"}
    text = "intro\n\n```py\nprint(1)\n```\n\nafter"
    out = transform(text, cfg)
    assert "print(1)" not in out
    assert "intro" in out and "after" in out


def test_transform_describes_code_fence_in_direct_mode():
    cfg = {"mode": "direct"}
    text = "```py\nprint(1)\nprint(2)\n```"
    out = transform(text, cfg)
    assert "code block" in out.lower()


def test_transform_passes_audible_block_through():
    cfg = {"mode": "brief"}
    text = "## Audible Summary\nHello there.\n\nMore prose with `not_an_audible`."
    out = transform(text, cfg)
    assert "Audible Summary" in out
    assert "Hello there" in out


def test_transform_drops_system_reminder():
    cfg = {"mode": "direct"}
    text = "before <system-reminder>secret</system-reminder> after"
    out = transform(text, cfg)
    assert "secret" not in out
    assert "before" in out and "after" in out


def test_transform_user_override_beats_preset():
    cfg = {"mode": "direct", "markup": {"code_fence": {"kind": "skip"}}}
    text = "```py\nx\n```"
    assert transform(text, cfg) == ""


def test_transform_invalid_user_kind_falls_back_to_preset():
    cfg = {"mode": "brief", "markup": {"code_fence": {"kind": "bogus"}}}
    out = transform("```\nx\n```", cfg)
    assert out == ""  # brief preset = skip


def test_transform_event_for_todo_update():
    cfg = {"mode": "brief"}
    event = {
        "kind": "tool_use", "name": "TodoWrite",
        "input": {"todos": [{"status": "completed", "content": "a"}]},
    }
    out = transform_event(event, cfg)
    assert out is not None and "1" in out
