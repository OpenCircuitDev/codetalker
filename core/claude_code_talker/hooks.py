"""Hook entry points called by the MCP server in response to Claude Code events."""
from __future__ import annotations

from claude_code_talker.transcript import collect_turn


async def handle_stop(payload, cfg, mode_a, mode_b, active_mode):
    """Handle a Stop event. Returns the speakable text (or "" to mute)."""
    if not cfg.get("enabled", True):
        return ""

    transcript = payload.get("transcript_path")
    if not transcript:
        return ""

    prose, tool_uses, todos = collect_turn(transcript)
    if not prose and not tool_uses and not todos:
        return ""

    if active_mode == "brief" and mode_b is not None:
        return await mode_b.build_async(prose, tool_uses, todos, cfg)
    if active_mode == "direct" and mode_a is not None:
        return mode_a.build(prose, tool_uses, todos, cfg)
    return ""


def handle_notification(payload, cfg):
    """Handle a Notification event. Returns the speakable text."""
    if not cfg.get("enabled", True):
        return ""
    msg = payload.get("message", "")
    if not msg:
        return ""
    return f"Claude. {msg}"
