"""Stdio MCP shim that proxies tool calls to the local HTTP daemon.

Spawned by Claude Code as the `codetalker` MCP server (see
`claude-code-plugin/.mcp.json`). On startup ensures the singleton daemon is
running, then forwards every tool call over the daemon's SSE endpoint. This
keeps the v0.3.0 multi-session contract intact: one daemon serves all
Claude Code sessions and the VS Code extension simultaneously.

Each Claude Code session spawns one shim; all shims share the daemon.
"""
from __future__ import annotations

import asyncio
import sys
import time

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from claude_code_talker.daemon import (
    DAEMON_HOST,
    DAEMON_PIDFILE,
    DAEMON_PORT,
    daemon_url,
    is_process_alive,
    read_pidfile,
    spawn_detached,
)


_HEALTH_URL = f"http://{DAEMON_HOST}:{DAEMON_PORT}/api/health"


_PROXY_TOOLS: list[Tool] = [
    Tool(
        name="tts_speak",
        description="Speak the given text using the active engine.",
        inputSchema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": True,
        },
    ),
    Tool(
        name="tts_set_mode",
        description="Switch active mode. mode: direct | brief | live | trigger.",
        inputSchema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["direct", "brief", "live", "trigger"]}
            },
            "required": ["mode"],
            "additionalProperties": True,
        },
    ),
    Tool(
        name="tts_status",
        description="Report current state: mode, mute, engines, providers.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": True},
    ),
    Tool(
        name="tts_mute",
        description="Mute TTS without changing config.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": True},
    ),
    Tool(
        name="tts_unmute",
        description="Unmute TTS.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": True},
    ),
    Tool(
        name="tts_list_voices",
        description="List available voices for an engine. engine defaults to piper.",
        inputSchema={
            "type": "object",
            "properties": {"engine": {"type": "string"}},
            "additionalProperties": True,
        },
    ),
    Tool(
        name="tts_set_voice",
        description="Set the active voice (model name). Optional engine arg switches engine too.",
        inputSchema={
            "type": "object",
            "properties": {
                "voice": {"type": "string"},
                "engine": {"type": "string"},
            },
            "required": ["voice"],
            "additionalProperties": True,
        },
    ),
    Tool(
        name="tts_set_cadence",
        description="Set the live-mode cadence: periodic | per_tool_call | per_cluster | significant_only | hybrid.",
        inputSchema={
            "type": "object",
            "properties": {
                "cadence": {
                    "type": "string",
                    "enum": [
                        "periodic",
                        "per_tool_call",
                        "per_cluster",
                        "significant_only",
                        "hybrid",
                    ],
                }
            },
            "required": ["cadence"],
            "additionalProperties": True,
        },
    ),
    Tool(
        name="tts_shutdown",
        description="Gracefully shut down the daemon process.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": True},
    ),
]


def _ensure_daemon_with_timeout(timeout_s: float = 10.0) -> bool:
    """Ensure the singleton daemon is up. Returns True if healthy within timeout."""
    pid = read_pidfile(DAEMON_PIDFILE)
    if pid is not None and is_process_alive(pid):
        try:
            r = httpx.get(_HEALTH_URL, timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    spawn_detached([sys.executable, "-m", "claude_code_talker", "serve"])
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(_HEALTH_URL, timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


async def _proxy_call(tool_name: str, args: dict) -> str:
    async with sse_client(daemon_url()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            for c in result.content:
                if hasattr(c, "text"):
                    return c.text
            return ""


def main() -> None:
    if not _ensure_daemon_with_timeout():
        print(
            "codetalker daemon failed to start. "
            "Is `claude-code-talker` on PATH? Try: pip install --user claude-code-talker",
            file=sys.stderr,
        )
        sys.exit(1)

    server: Server = Server("codetalker-stdio")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return _PROXY_TOOLS

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[TextContent]:
        try:
            text = await asyncio.wait_for(
                _proxy_call(name, arguments or {}), timeout=15.0
            )
        except asyncio.TimeoutError:
            text = f"error: timed out calling {name} on daemon"
        except Exception as e:
            text = f"error: {e}"
        return [TextContent(type="text", text=text)]

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="codetalker",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
