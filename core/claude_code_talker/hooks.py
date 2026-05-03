"""Hook entry points called by the MCP server in response to Claude Code events."""
from __future__ import annotations

from claude_code_talker.transcript import collect_turn


async def handle_stop(payload, cfg, mode_a, mode_b, active_mode):
    """Handle a Stop event. Returns the speakable text (or "" to mute).

    Live mode normally returns "" because the cadence loop owns the audio.
    But cfg.briefs.always_brief_on_stop (default True) makes Stop ALSO emit a
    Brief even when active_mode is "live" — so the user hears a wrap-up at
    end-of-turn (which the cadence loop doesn't naturally provide).
    """
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
    if active_mode == "live":
        # Live + brief combo: even though cadence loop owns the in-flight
        # narration, fire a Brief on Stop so the user hears a wrap-up of
        # what just completed.  Toggleable via cfg.briefs.always_brief_on_stop.
        if (cfg.get("briefs") or {}).get("always_brief_on_stop", True) and mode_b is not None:
            return await mode_b.build_async(prose, tool_uses, todos, cfg)
    return ""


def handle_notification(payload, cfg):
    """Handle a Notification event. Returns the speakable text."""
    if not cfg.get("enabled", True):
        return ""
    msg = payload.get("message", "")
    if not msg:
        return ""
    return f"Claude. {msg}"


PROMPT_BRIEF_TEMPLATE = """\
The user just submitted this prompt to Claude Code:

\"\"\"{prompt}\"\"\"

In ONE SHORT SENTENCE (max 25 words) of plain spoken English, summarize what
the user is asking and what Claude is likely to do. Lead with the action
("The user wants...", "The user is asking..."). Skip greetings.

BRIEF:"""


async def handle_user_prompt_submit(payload, cfg, provider):
    """Handle a UserPromptSubmit hook event.

    Calls the LLM to produce a one-sentence "the user wants X" briefing
    suitable for live audio narration. Returns the briefing text or "" if
    disabled / empty / provider unavailable.
    """
    if not cfg.get("enabled", True):
        return ""
    briefs_cfg = (cfg.get("briefs") or {})
    if not briefs_cfg.get("user_prompt_enabled", True):
        return ""
    prompt = payload.get("prompt") or ""
    prompt = prompt.strip()
    if not prompt:
        return ""
    if provider is None:
        # No LLM available — fall back to a literal summary.
        snippet = prompt[:120].replace("\n", " ")
        return f"You just asked: {snippet}"
    try:
        text = await provider.complete(
            PROMPT_BRIEF_TEMPLATE.format(prompt=prompt[:1500]),
            max_tokens=80,
        )
        return (text or "").strip()
    except Exception:
        snippet = prompt[:120].replace("\n", " ")
        return f"You just asked: {snippet}"
