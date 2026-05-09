"""CCT-31 — Windows screen capture wrapped behind a stable interface.

Uses dxcam for fullscreen + region capture (Windows-only). On other platforms
or when dxcam isn't installed, returns None so the caller can degrade.
"""
from __future__ import annotations

import io
from typing import Optional

try:
    import dxcam  # type: ignore
    _DXCAM = dxcam.create()
except (ImportError, RuntimeError):
    _DXCAM = None

try:
    from PIL import Image  # type: ignore
except ImportError:
    Image = None  # type: ignore


def _dxcam_grab():
    if _DXCAM is None:
        raise ImportError("dxcam not available")
    return _DXCAM.grab()


def _dxcam_grab_region(region):
    if _DXCAM is None:
        raise ImportError("dxcam not available")
    return _DXCAM.grab(region=region)


def _find_window_by_title(title_substring: str) -> tuple[int, int, int, int] | None:
    try:
        import win32gui  # type: ignore
    except ImportError:
        return None
    found: list[tuple[int, int, int, int]] = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd) or ""
        if title_substring.lower() in title.lower():
            rect = win32gui.GetWindowRect(hwnd)
            found.append(rect)

    win32gui.EnumWindows(_enum, None)
    return found[0] if found else None


def _encode_jpeg(frame, quality: int = 70) -> bytes:
    if Image is None:
        return b""
    img = Image.fromarray(frame)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class ScreenCaptureSource:
    def capture_fullscreen(self) -> Optional[bytes]:
        try:
            frame = _dxcam_grab()
            if frame is None:
                return None
            return _encode_jpeg(frame)
        except (ImportError, Exception):
            return None

    def capture_window(self, title_substring: str) -> Optional[bytes]:
        rect = _find_window_by_title(title_substring)
        if rect is None:
            return None
        try:
            frame = _dxcam_grab_region(rect)
            if frame is None:
                return None
            return _encode_jpeg(frame)
        except (ImportError, Exception):
            return None
