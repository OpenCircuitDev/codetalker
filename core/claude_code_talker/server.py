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


from dataclasses import dataclass as _dc


@_dc
class MCPTool:
    name: str
    description: str
    handler: object  # async callable


class MCPServer:
    """Thin server that hosts a registry of named tools and dispatches calls.

    Phase 1: testable in isolation. Phase 2: wire to the official mcp SDK
    transport (stdio/SSE) without changing the tool implementations.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool):
        self._tools[tool.name] = tool

    def list_tools(self):
        return list(self._tools.values())

    async def call_tool(self, name: str, args: dict) -> str:
        if name not in self._tools:
            raise ValueError(f"unknown tool: {name}")
        return await self._tools[name].handler(args)


def build_mcp_server(state: ServerState) -> MCPServer:
    """Register all Phase 1 tools on a fresh MCPServer."""
    server = MCPServer()

    async def tts_speak(args):
        text = args.get("text", "")
        if not text:
            return "no text"
        # Phase 1 synthesizes through the active engine and plays.
        # Implementation deferred to Task 14 to keep this task focused.
        return f"would speak: {text[:80]}"

    async def tts_set_mode(args):
        mode = args.get("mode")
        if mode not in state.modes:
            raise ValueError(f"unknown mode: {mode}; available: {list(state.modes)}")
        state.active_mode = mode
        return f"active mode set to {mode}"

    async def tts_status(args):
        enabled = state.cfg.get("enabled", True)
        return (
            f"mode={state.active_mode}, "
            f"{'enabled' if enabled else 'muted'}, "
            f"engines={list(state.engines)}, "
            f"providers={list(state.providers)}"
        )

    async def tts_mute(args):
        state.cfg["enabled"] = False
        return "muted"

    async def tts_unmute(args):
        state.cfg["enabled"] = True
        return "unmuted"

    async def tts_list_voices(args):
        engine_name = args.get("engine") or "piper"
        engine = state.engines.get(engine_name)
        if not engine:
            raise ValueError(f"unknown engine: {engine_name}")
        return ", ".join(engine.list_voices())

    server.register(MCPTool("tts_speak", "Speak the given text using the active engine.", tts_speak))
    server.register(MCPTool("tts_set_mode", "Switch active mode: direct or brief.", tts_set_mode))
    server.register(MCPTool("tts_status", "Report current state.", tts_status))
    server.register(MCPTool("tts_mute", "Mute TTS without changing config.", tts_mute))
    server.register(MCPTool("tts_unmute", "Unmute TTS.", tts_unmute))
    server.register(MCPTool("tts_list_voices", "List available voices for an engine.", tts_list_voices))

    return server
