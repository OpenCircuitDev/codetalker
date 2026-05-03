"""CLI entry point invoked by Claude Code hooks.

Reads JSON from stdin, identifies the event, posts the appropriate MCP
tool call to the running daemon. If the daemon isn't running, spawns it
detached and exits silently.
"""
from __future__ import annotations

import asyncio
import json
import sys

from claude_code_talker.daemon import (
    DAEMON_PIDFILE, daemon_url, is_process_alive, read_pidfile, spawn_detached,
)


async def _call_mcp_tool(tool_name: str, args: dict) -> str:
    """Connect to the daemon's SSE endpoint and call the named MCP tool.

    Raises ConnectionRefusedError if the daemon isn't reachable.
    """
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(daemon_url()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            # FastMCP returns content list; extract text.
            for c in result.content:
                if hasattr(c, "text"):
                    return c.text
            return ""


def _ensure_daemon() -> None:
    """If the daemon isn't running, spawn it detached. No-op if running."""
    pid = read_pidfile(DAEMON_PIDFILE)
    if pid is not None and is_process_alive(pid):
        return  # already running
    # Spawn detached. Use sys.executable to ensure the same Python.
    spawn_detached([sys.executable, "-m", "claude_code_talker", "serve"])


async def dispatch_hook(payload: dict) -> None:
    event = payload.get("hook_event_name", "")
    # session_id + cwd flow into every MCP tool call so per-session config works.
    common = {
        "session_id": payload.get("session_id", ""),
        "cwd": payload.get("cwd", ""),
    }

    if event == "Stop":
        tool_args = {**common, "transcript_path": payload.get("transcript_path", "")}
        tool_name = "tts_handle_stop"
    elif event == "Notification":
        tool_args = {**common, "message": payload.get("message", "")}
        tool_name = "tts_handle_notification"
    elif event == "PreToolUse":
        tool_args = {
            **common,
            "tool_name": payload.get("tool_name", ""),
            "tool_input": payload.get("tool_input", {}),
        }
        tool_name = "tts_handle_pretool"
    elif event == "PostToolUse":
        tool_args = {
            **common,
            "tool_name": payload.get("tool_name", ""),
            "tool_input": payload.get("tool_input", {}),
            "tool_response": payload.get("tool_response", {}),
        }
        tool_name = "tts_handle_posttool"
    else:
        return  # unknown event — silent no-op

    try:
        # Timeout sized for Python cold-start + SSE handshake (~2-3s on Windows/Dropbox)
        # plus the actual tool dispatch. Hook events run with `async: true` in Claude Code's
        # hook config so the user's chat never blocks on us — we just need to finish before
        # the OS reaps the process.
        await asyncio.wait_for(_call_mcp_tool(tool_name, tool_args), timeout=10.0)
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        # Daemon not reachable. Spawn it detached and exit silently.
        # Next hook will succeed.
        try:
            _ensure_daemon()
        except Exception:
            pass


def main():
    raw = sys.stdin.read()
    # Debug: every invocation appended to ~/.claude/scripts/codetalker_hook_invocations.log
    try:
        from pathlib import Path
        import time
        log = Path.home() / ".claude" / "scripts" / "codetalker_hook_invocations.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} stdin_bytes={len(raw)} preview={raw[:200]!r}\n")
    except Exception:
        pass
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return
    asyncio.run(dispatch_hook(payload))


if __name__ == "__main__":
    main()
