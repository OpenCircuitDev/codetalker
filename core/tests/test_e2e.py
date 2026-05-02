"""End-to-end integration test for Phase 1.

Validates that a Stop event payload flows through the full pipeline and ends
in a synthesize+play call with the expected text.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from claude_code_talker.hook_cli import dispatch_hook


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_e2e_stop_flow_produces_audio_synth_call(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "Investigate."}]}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Smoking gun found. The skeleton ref pose is in meters."}]}}) + "\n"
    )

    payload = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
    }

    fake_engine = MagicMock()
    fake_engine.synthesize = MagicMock(return_value=b"FAKE_WAV")
    fake_engine.list_voices = MagicMock(return_value=["en_GB-jenny_dioco-medium"])

    with patch("claude_code_talker.hook_cli.PiperEngine", return_value=fake_engine), \
         patch("claude_code_talker.hook_cli.play_wav_bytes") as mock_play, \
         patch("claude_code_talker.hook_cli.load_full_config", return_value={
            "enabled": True,
            "voice": {"model": "en_GB-jenny_dioco-medium", "rate": 1.0},
            "elements": {"heading": True, "code_block": False, "inline_code": True,
                         "link": True, "list": True, "blockquote": True,
                         "emphasis": True, "table": False, "insight_block": False},
            "urls": {"shorten_to_host": True},
            "paths": {"handling": "filename"},
            "content_filter": {"mode": "off"},
            "text": {"max_chars": 5000, "boundary_snap": "sentence", "truncation_marker": "..."},
            "synopsis": {"enabled": False},
            "active_mode": "direct",
         }):
        await dispatch_hook(payload)

    fake_engine.synthesize.assert_called_once()
    spoken_text = fake_engine.synthesize.call_args[0][0]
    assert "Smoking gun" in spoken_text
    mock_play.assert_called_once_with(b"FAKE_WAV")


@pytest.mark.asyncio
async def test_e2e_notification_flow(tmp_path):
    payload = {
        "hook_event_name": "Notification",
        "message": "Permission required.",
    }

    fake_engine = MagicMock()
    fake_engine.synthesize = MagicMock(return_value=b"WAV")
    fake_engine.list_voices = MagicMock(return_value=["jenny"])

    with patch("claude_code_talker.hook_cli.PiperEngine", return_value=fake_engine), \
         patch("claude_code_talker.hook_cli.play_wav_bytes") as mock_play, \
         patch("claude_code_talker.hook_cli.load_full_config", return_value={
            "enabled": True,
            "voice": {"model": "jenny", "rate": 1.0},
         }):
        await dispatch_hook(payload)

    fake_engine.synthesize.assert_called_once()
    spoken = fake_engine.synthesize.call_args[0][0]
    assert "Claude. Permission required." in spoken


@pytest.mark.asyncio
async def test_e2e_disabled_skips_everything(tmp_path):
    payload = {"hook_event_name": "Stop", "transcript_path": str(tmp_path / "x.jsonl")}

    fake_engine = MagicMock()
    with patch("claude_code_talker.hook_cli.PiperEngine", return_value=fake_engine), \
         patch("claude_code_talker.hook_cli.play_wav_bytes") as mock_play, \
         patch("claude_code_talker.hook_cli.load_full_config", return_value={"enabled": False}):
        await dispatch_hook(payload)

    fake_engine.synthesize.assert_not_called()
    mock_play.assert_not_called()
