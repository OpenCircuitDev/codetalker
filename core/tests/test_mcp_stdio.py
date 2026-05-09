"""Phase 18.2 — sanity tests for the stdio MCP shim.

Full subprocess round-trip is brittle on CI; these tests exercise the in-process
seams (tool list, daemon-down handling) and rely on `test_e2e.py` for the
actual SSE round-trip via the daemon.
"""
from unittest.mock import patch

import pytest

from claude_code_talker import mcp_stdio
from claude_code_talker.mcp_stdio import _PROXY_TOOLS, _ensure_daemon_with_timeout


_EXPECTED_TOOL_NAMES = {
    "tts_speak",
    "tts_set_mode",
    "tts_status",
    "tts_mute",
    "tts_unmute",
    "tts_list_voices",
    "tts_set_voice",
    "tts_set_cadence",
    "tts_shutdown",
}


def test_proxy_tool_count_is_nine():
    assert len(_PROXY_TOOLS) == 9


def test_proxy_tool_names_match_expected_set():
    actual = {t.name for t in _PROXY_TOOLS}
    assert actual == _EXPECTED_TOOL_NAMES


def test_proxy_tools_have_input_schemas():
    for t in _PROXY_TOOLS:
        assert t.inputSchema is not None
        assert t.inputSchema.get("type") == "object"


def test_proxy_tools_skip_internal_hook_handlers():
    """tts_handle_* tools are CLI-internal plumbing; they must NOT be proxied."""
    actual = {t.name for t in _PROXY_TOOLS}
    for forbidden in (
        "tts_handle_stop",
        "tts_handle_notification",
        "tts_handle_user_prompt_submit",
        "tts_handle_pretool",
        "tts_handle_posttool",
    ):
        assert forbidden not in actual


def test_set_voice_schema_requires_voice():
    set_voice = next(t for t in _PROXY_TOOLS if t.name == "tts_set_voice")
    assert "voice" in set_voice.inputSchema.get("required", [])


def test_set_cadence_schema_constrains_enum():
    set_cadence = next(t for t in _PROXY_TOOLS if t.name == "tts_set_cadence")
    enum = set_cadence.inputSchema["properties"]["cadence"]["enum"]
    assert set(enum) == {
        "periodic",
        "per_tool_call",
        "per_cluster",
        "significant_only",
        "hybrid",
    }


def test_ensure_daemon_returns_false_when_unreachable_quickly(monkeypatch):
    """Daemon-down case: spawn fails or health never responds within timeout."""
    # Force is_process_alive False so the function tries to spawn.
    monkeypatch.setattr(mcp_stdio, "read_pidfile", lambda _: None)
    # Spawn no-ops in the test (don't actually launch the daemon).
    monkeypatch.setattr(mcp_stdio, "spawn_detached", lambda *a, **k: 0)

    class _FailingHttpx:
        def get(self, *a, **k):
            raise ConnectionError("test: daemon unreachable")

    monkeypatch.setattr(mcp_stdio, "httpx", _FailingHttpx())
    # Use a tiny timeout so the test finishes quickly.
    assert _ensure_daemon_with_timeout(timeout_s=0.5) is False


def test_ensure_daemon_returns_true_when_pidfile_alive_and_healthy(monkeypatch):
    monkeypatch.setattr(mcp_stdio, "read_pidfile", lambda _: 12345)
    monkeypatch.setattr(mcp_stdio, "is_process_alive", lambda _: True)

    class _OkResp:
        status_code = 200

    class _OkHttpx:
        def get(self, *a, **k):
            return _OkResp()

    monkeypatch.setattr(mcp_stdio, "httpx", _OkHttpx())
    assert _ensure_daemon_with_timeout(timeout_s=0.5) is True
