"""MCP server entry point + tool registry.

This is the single long-running process. Hooks and extensions both talk to it.
Phase 1 wires Stop and Notification handlers; Phase 2 adds PreToolUse and
PostToolUse for live narration.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from claude_code_talker.audio import AudioJob, AudioQueue
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
    audio_queue: AudioQueue = None  # set in build_server_state
    shutting_down: bool = False


def build_server_state(cwd: str | None = None) -> ServerState:
    """Construct the server state with all engines, providers, and modes registered."""
    cfg = load_full_config(cwd=cwd)

    piper = PiperEngine(piper_exe=PIPER_DIR / "piper.exe", voices_dir=VOICES_DIR)
    ollama = OllamaProvider()

    modes: dict[str, ModeStrategy] = {
        "direct": DirectMode(),
        "brief": BriefMode(provider=ollama),
    }

    state = ServerState(
        cfg=cfg,
        engines={"piper": piper},
        providers={"ollama": ollama},
        modes=modes,
        active_mode="direct",
    )
    state.audio_queue = AudioQueue(state)
    state.audio_queue.start()
    return state


def main():
    """Entry point for the `claude-code-talker` CLI command.

    Subcommands:
      claude-code-talker          - print status (legacy summary)
      claude-code-talker serve    - run as foreground daemon
      claude-code-talker stop     - send tts_shutdown to running daemon (Task 13)
    """
    import sys
    args = sys.argv[1:]
    if args and args[0] == "serve":
        from claude_code_talker.daemon import serve_foreground
        serve_foreground()
        return
    if args and args[0] == "stop":
        from claude_code_talker.daemon import stop_daemon
        stop_daemon()
        return

    state = build_server_state()
    print(f"claude-code-talker server initialized")
    print(f"  engines: {list(state.engines)}")
    print(f"  providers: {list(state.providers)}")
    print(f"  modes: {list(state.modes)}")
    print(f"  active mode: {state.active_mode}")
    print("Use 'claude-code-talker serve' to start the daemon.")


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


def register_tools(server, state) -> None:
    """Register all 7 Phase 2A tools on a server instance.

    The server must expose a `.register(MCPTool)` method. This works for both
    our in-process MCPServer (Phase 1, used in tests) and a thin adapter
    around the mcp SDK FastMCP server (production, lands in Phase 2A.3).
    """

    async def tts_speak(args):
        text = args.get("text", "")
        if not text:
            return "skipped: no text"
        if not state.cfg.get("enabled", True):
            return "skipped: muted"
        engine_name = (state.cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        if not engine:
            raise ValueError(f"engine not registered: {engine_name}")
        voice = (state.cfg.get("voice") or {}).get("model")
        rate = float((state.cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices()
            if not voices:
                return "skipped: no voices available"
            voice = voices[0]
        state.audio_queue.submit(AudioJob(text=text, voice=voice, rate=rate, engine_name=engine_name))
        return f"queued: {len(text)} chars"

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

    async def tts_shutdown(args):
        state.shutting_down = True
        # The actual process exit happens in the daemon's main loop, which
        # checks state.shutting_down and exits gracefully (Task 13).
        return "shutting down"

    async def tts_handle_stop(args):
        from claude_code_talker.hooks import handle_stop
        if not state.cfg.get("enabled", True):
            return "skipped: muted"
        text = await handle_stop(
            payload={"transcript_path": args.get("transcript_path", ""), "cwd": args.get("cwd", "")},
            cfg=state.cfg,
            mode_a=state.modes.get("direct"),
            mode_b=state.modes.get("brief"),
            active_mode=state.active_mode,
        )
        if not text:
            return "skipped: no text"
        engine_name = (state.cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        voice = (state.cfg.get("voice") or {}).get("model")
        rate = float((state.cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices()
            if not voices:
                return "skipped: no voices"
            voice = voices[0]
        state.audio_queue.submit(AudioJob(text=text, voice=voice, rate=rate, engine_name=engine_name))
        return f"queued: {len(text)} chars"

    async def tts_handle_notification(args):
        from claude_code_talker.hooks import handle_notification
        text = handle_notification(
            payload={"message": args.get("message", "")},
            cfg=state.cfg,
        )
        if not text:
            return "skipped: no text"
        engine_name = (state.cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        voice = (state.cfg.get("voice") or {}).get("model")
        rate = float((state.cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices()
            if not voices:
                return "skipped: no voices"
            voice = voices[0]
        state.audio_queue.submit(AudioJob(text=text, voice=voice, rate=rate, engine_name=engine_name))
        return f"queued: {len(text)} chars"

    server.register(MCPTool("tts_speak", "Speak the given text using the active engine.", tts_speak))
    server.register(MCPTool("tts_set_mode", "Switch active mode: direct or brief.", tts_set_mode))
    server.register(MCPTool("tts_status", "Report current state.", tts_status))
    server.register(MCPTool("tts_mute", "Mute TTS without changing config.", tts_mute))
    server.register(MCPTool("tts_unmute", "Unmute TTS.", tts_unmute))
    server.register(MCPTool("tts_list_voices", "List available voices for an engine.", tts_list_voices))
    server.register(MCPTool("tts_shutdown", "Gracefully shut down the daemon.", tts_shutdown))
    server.register(MCPTool("tts_handle_stop", "Handle a Stop hook event.", tts_handle_stop))
    server.register(MCPTool("tts_handle_notification", "Handle a Notification hook event.", tts_handle_notification))


def build_mcp_server(state: ServerState) -> MCPServer:
    """Register the Phase 2A tools on a fresh in-process MCPServer."""
    server = MCPServer()
    register_tools(server, state)
    return server


def _register_tools_fastmcp(fmcp, state) -> None:
    """Register the 9 tools on a FastMCP instance by bridging the in-process handlers.

    Our in-process handlers take a single ``args: dict`` argument.  FastMCP
    introspects function signatures to build Pydantic argument models; using
    ``**kwargs`` causes it to create a schema with a single required ``kwargs``
    field rather than an open schema.  We bypass that by adding each tool
    directly to the tool manager with a hand-crafted ``FuncMetadata`` that
    accepts arbitrary keyword arguments and forwards them as a plain dict.
    """
    from mcp.server.fastmcp.tools.base import Tool as _FastTool
    from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata as _FuncMeta, ArgModelBase as _ArgBase
    from pydantic import ConfigDict as _ConfigDict

    class _OpenArgModel(_ArgBase):
        """Accepts any keyword arguments; passes them through as a plain dict."""
        model_config = _ConfigDict(arbitrary_types_allowed=True, extra="allow")

        def model_dump_one_level(self):
            base = super().model_dump_one_level()
            if self.model_extra:
                base.update(self.model_extra)
            return base

    _open_meta = _FuncMeta(arg_model=_OpenArgModel, wrap_output=False)

    inproc = MCPServer()
    register_tools(inproc, state)

    for tool in inproc.list_tools():
        # Capture tool in closure so each wrapper gets its own reference.
        def _make_wrapper(t: MCPTool):
            async def _handler(**kwargs: object) -> str:
                return await t.handler(kwargs)
            _handler.__name__ = t.name
            _handler.__doc__ = t.description
            return _handler

        wrapper = _make_wrapper(tool)
        fast_tool = _FastTool(
            fn=wrapper,
            name=tool.name,
            description=tool.description,
            parameters={"type": "object", "properties": {}, "additionalProperties": True},
            fn_metadata=_open_meta,
            is_async=True,
        )
        fmcp._tool_manager._tools[tool.name] = fast_tool


def build_asgi_app(state: ServerState, *, disable_transport_security: bool = False):
    """Build a Starlette ASGI app that serves all 9 tools over MCP-over-SSE.

    The returned app exposes:
      GET  /sse        -- SSE connection endpoint for MCP clients
      POST /messages   -- client-to-server message channel

    Args:
        state: Populated ServerState from build_server_state().
        disable_transport_security: Set True in tests (ASGI transport has no real
            Host header that satisfies the SDK's DNS-rebinding allowlist).  In
            production the daemon binds to 127.0.0.1 and the allowlist is set
            to the daemon's own address.
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    if disable_transport_security:
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    else:
        # Allow only the loopback address the daemon listens on (127.0.0.1:17832).
        # These constants mirror daemon.DAEMON_HOST / DAEMON_PORT; they are not
        # imported from daemon.py to avoid a circular dependency.
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:17832", "127.0.0.1", "localhost"],
        )

    fmcp = FastMCP("claude-code-talker", transport_security=security)
    _register_tools_fastmcp(fmcp, state)

    # sse_app() returns a pre-wired Starlette application with /sse and /messages
    # routes already configured.  No manual Route/Mount plumbing required.
    return fmcp.sse_app()
