"""Tests for hook entry points."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.hooks import handle_stop, handle_notification


@pytest.mark.asyncio
async def test_handle_stop_returns_speakable_text(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Response paragraph."}]}}) + "\n"
    )

    cfg = {
        "enabled": True,
        "elements": {"heading": True, "code_block": False, "inline_code": True,
                     "link": True, "list": True, "blockquote": True,
                     "emphasis": True, "table": False, "insight_block": False},
        "urls": {"shorten_to_host": True},
        "paths": {"handling": "filename"},
        "content_filter": {"mode": "off"},
        "text": {"max_chars": 5000, "boundary_snap": "sentence", "truncation_marker": "..."},
        "synopsis": {"enabled": False},
    }
    mode = MagicMock()
    mode.build = MagicMock(return_value="Response paragraph.")

    result = await handle_stop(
        payload={"transcript_path": str(transcript)},
        cfg=cfg,
        mode_a=mode,
        mode_b=None,
        active_mode="direct",
    )
    assert result == "Response paragraph."


@pytest.mark.asyncio
async def test_handle_stop_returns_empty_when_disabled(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")
    result = await handle_stop(
        payload={"transcript_path": str(transcript)},
        cfg={"enabled": False},
        mode_a=None, mode_b=None, active_mode="direct",
    )
    assert result == ""


@pytest.mark.asyncio
async def test_handle_stop_uses_brief_when_active_mode_brief(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "go"}]}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}) + "\n"
    )

    mode_b = MagicMock()
    mode_b.build_async = AsyncMock(return_value="Brief result.")

    result = await handle_stop(
        payload={"transcript_path": str(transcript)},
        cfg={"enabled": True},
        mode_a=None, mode_b=mode_b, active_mode="brief",
    )
    assert result == "Brief result."


def test_handle_notification_returns_prefixed_message():
    result = handle_notification(
        payload={"message": "Permission needed."},
        cfg={"enabled": True},
    )
    assert result == "Claude. Permission needed."


def test_handle_notification_returns_empty_when_disabled():
    result = handle_notification(
        payload={"message": "x"},
        cfg={"enabled": False},
    )
    assert result == ""
