"""CCT-31 — screen capture source tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from claude_code_talker.companion.screen_capture import ScreenCaptureSource


def test_capture_fullscreen_returns_jpeg_bytes():
    fake_frame = MagicMock()
    fake_frame.tobytes.return_value = b"raw-pixels"
    with patch("claude_code_talker.companion.screen_capture._dxcam_grab", return_value=fake_frame), \
         patch("claude_code_talker.companion.screen_capture._encode_jpeg", return_value=b"jpeg-bytes"):
        s = ScreenCaptureSource()
        assert s.capture_fullscreen() == b"jpeg-bytes"


def test_capture_fullscreen_handles_missing_dxcam_gracefully():
    with patch("claude_code_talker.companion.screen_capture._dxcam_grab", side_effect=ImportError):
        s = ScreenCaptureSource()
        assert s.capture_fullscreen() is None


def test_capture_window_returns_jpeg_when_window_found():
    fake_frame = MagicMock()
    with patch("claude_code_talker.companion.screen_capture._find_window_by_title", return_value=(0, 0, 800, 600)), \
         patch("claude_code_talker.companion.screen_capture._dxcam_grab_region", return_value=fake_frame), \
         patch("claude_code_talker.companion.screen_capture._encode_jpeg", return_value=b"jpeg"):
        s = ScreenCaptureSource()
        assert s.capture_window("Claude Code") == b"jpeg"


def test_capture_window_returns_none_if_window_missing():
    with patch("claude_code_talker.companion.screen_capture._find_window_by_title", return_value=None):
        s = ScreenCaptureSource()
        assert s.capture_window("Nonexistent") is None
