"""Tests for Phase 14.5 trigger-mode branch in LiveMode."""
import pytest
from unittest.mock import MagicMock
from claude_code_talker.modes.live import LiveMode
from claude_code_talker.event_buffer import EventBuffer
from claude_code_talker.cadence.periodic import PeriodicCadence


def _make_live_mode(*, mode: str, enabled_tags: dict | None = None) -> LiveMode:
    """Construct a LiveMode wired with cfg + a mock audio_queue."""
    cfg = {
        "live": {"mode": mode},
        "triggers": {"tags": enabled_tags or {}},
        "voice": {"model": "test-voice", "rate": 1.0, "engine": "piper"},
    }
    audio_queue = MagicMock()
    audio_queue.submit = MagicMock()

    sessions = MagicMock()
    sessions.get = MagicMock(return_value=None)
    sessions.config_for = MagicMock(return_value=cfg)

    narration_log = MagicMock()
    narration_log.append = MagicMock()

    return LiveMode(
        provider=MagicMock(),
        cadence=PeriodicCadence(period_seconds=60.0),
        event_buffer=EventBuffer(),
        audio_queue=audio_queue,
        cfg=cfg,
        narration_log=narration_log,
        sessions=sessions,
    )


def test_trigger_mode_with_tagged_prose_submits_audio_job():
    enabled = {
        "audible_summary": {
            "display_name": "Audible Summary",
            "enabled": True,
            "editor_mode": "structured",
        }
    }
    live = _make_live_mode(mode="trigger", enabled_tags=enabled)
    prose = "## Audible Summary\nI'm doing the thing."
    live._trigger_handler("sess-A", prose)
    assert live.audio_queue.submit.call_count == 1
    job = live.audio_queue.submit.call_args[0][0]
    assert "doing the thing" in job.text
    assert job.voice == "test-voice"


def test_trigger_mode_with_untagged_prose_no_audio_job():
    enabled = {"audible_summary": {"display_name": "Audible Summary", "enabled": True}}
    live = _make_live_mode(mode="trigger", enabled_tags=enabled)
    prose = "Just some normal text without any tagged blocks."
    live._trigger_handler("sess-A", prose)
    assert live.audio_queue.submit.call_count == 0


def test_llm_mode_skips_trigger_path():
    enabled = {"audible_summary": {"display_name": "Audible Summary", "enabled": True}}
    live = _make_live_mode(mode="llm", enabled_tags=enabled)
    prose = "## Audible Summary\nThis would fire in trigger mode."
    live._trigger_handler("sess-A", prose)
    assert live.audio_queue.submit.call_count == 0


def test_both_mode_fires_trigger_path():
    enabled = {"audible_summary": {"display_name": "Audible Summary", "enabled": True}}
    live = _make_live_mode(mode="both", enabled_tags=enabled)
    prose = "## Audible Summary\nBoth-mode test."
    live._trigger_handler("sess-A", prose)
    assert live.audio_queue.submit.call_count == 1


def test_trigger_mode_skips_disabled_tags():
    enabled = {
        "audible_summary": {"display_name": "Audible Summary", "enabled": False}
    }
    live = _make_live_mode(mode="trigger", enabled_tags=enabled)
    prose = "## Audible Summary\nThis tag is disabled."
    live._trigger_handler("sess-A", prose)
    assert live.audio_queue.submit.call_count == 0
