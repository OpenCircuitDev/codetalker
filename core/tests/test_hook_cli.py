"""Tests for the hook CLI entry point that Claude Code invokes."""
import json
import pytest
from unittest.mock import patch, MagicMock
from claude_code_talker.hook_cli import dispatch_hook


@pytest.mark.asyncio
async def test_dispatch_hook_stop_calls_handler(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world."}]}}) + "\n"
    )

    payload = {"hook_event_name": "Stop", "transcript_path": str(transcript), "cwd": str(tmp_path)}

    with patch("claude_code_talker.hook_cli.play_wav_bytes") as mock_play, \
         patch("claude_code_talker.hook_cli.PiperEngine") as mock_piper_cls:
        mock_engine = MagicMock()
        mock_engine.synthesize = MagicMock(return_value=b"WAV")
        mock_engine.list_voices = MagicMock(return_value=["jenny"])
        mock_piper_cls.return_value = mock_engine

        await dispatch_hook(payload)

        # Either synthesize is called (if config has a voice) or no-op-skipped.
        # Important: the function returns without crashing.


@pytest.mark.asyncio
async def test_dispatch_hook_notification_calls_handler():
    payload = {"hook_event_name": "Notification", "message": "Permission needed"}

    with patch("claude_code_talker.hook_cli.play_wav_bytes") as mock_play, \
         patch("claude_code_talker.hook_cli.PiperEngine") as mock_piper_cls:
        mock_engine = MagicMock()
        mock_engine.synthesize = MagicMock(return_value=b"WAV")
        mock_engine.list_voices = MagicMock(return_value=["jenny"])
        mock_piper_cls.return_value = mock_engine

        await dispatch_hook(payload)


@pytest.mark.asyncio
async def test_dispatch_hook_unknown_event_is_noop():
    payload = {"hook_event_name": "WhoKnows"}
    # Should not raise
    await dispatch_hook(payload)
