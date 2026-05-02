"""Tests for the MCP server skeleton."""
import pytest
from claude_code_talker.server import build_server_state


def test_build_server_state_loads_engines_providers_modes():
    state = build_server_state()
    assert "piper" in state.engines
    assert "ollama" in state.providers
    assert "direct" in state.modes
    assert "brief" in state.modes


def test_build_server_state_has_default_active_mode():
    state = build_server_state()
    assert state.active_mode in ("direct", "brief")


def test_build_server_state_loads_config():
    state = build_server_state()
    assert isinstance(state.cfg, dict)
    assert state.cfg.get("enabled", True) in (True, False)
