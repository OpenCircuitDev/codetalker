"""MCP server entry point + tool registry.

This is the single long-running process. Hooks and extensions both talk to it.
Phase 1 wires Stop and Notification handlers; Phase 2 adds PreToolUse and
PostToolUse for live narration.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from claude_code_talker.config import load_full_config
from claude_code_talker.engines import PiperEngine
from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.modes.direct import DirectMode
from claude_code_talker.modes.brief import BriefMode
from claude_code_talker.providers import OllamaProvider


PIPER_DIR = Path.home() / ".claude" / "scripts" / "piper" / "piper"
VOICES_DIR = Path.home() / ".claude" / "scripts" / "piper" / "voices"


@dataclass
class ServerState:
    cfg: dict
    engines: dict[str, object]
    providers: dict[str, object]
    modes: dict[str, ModeStrategy]
    active_mode: str = "direct"


def build_server_state(cwd: str | None = None) -> ServerState:
    """Construct the server state with all engines, providers, and modes registered."""
    cfg = load_full_config(cwd=cwd)

    piper = PiperEngine(piper_exe=PIPER_DIR / "piper.exe", voices_dir=VOICES_DIR)
    ollama = OllamaProvider()

    modes: dict[str, ModeStrategy] = {
        "direct": DirectMode(),
        "brief": BriefMode(provider=ollama),
    }

    return ServerState(
        cfg=cfg,
        engines={"piper": piper},
        providers={"ollama": ollama},
        modes=modes,
        active_mode="direct",
    )


def main():
    """Entry point for the `claude-code-talker` CLI command."""
    state = build_server_state()
    print(f"claude-code-talker server initialized")
    print(f"  engines: {list(state.engines)}")
    print(f"  providers: {list(state.providers)}")
    print(f"  modes: {list(state.modes)}")
    print(f"  active mode: {state.active_mode}")
    print("MCP server protocol wiring lands in Task 13.")


if __name__ == "__main__":
    main()
