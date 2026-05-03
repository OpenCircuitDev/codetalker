"""Teacher mode: prompt directives that re-shape narration for non-experts.

Teacher mode is a prompt-layer feature, not a content-filter. The LLM still sees
every event the buffer feeds it; we just append directives telling the LLM to
expand jargon, define terms inline, and/or reframe events as teaching moments.

User-locked spec 2026-05-03:
- depth_level: 1-5 slider (1=full expert, 5=full beginner with maximum framing)
- substitution: bool — swap technical terms for plain English
- glossary: bool — narrate jargon then define inline
- reframe: bool — restructure narration as a teaching moment

All four knobs are independent and toggleable globally and per-session.
"""
from __future__ import annotations


def teacher_directives(teacher_cfg: dict | None) -> str:
    """Return the directive block to inject into a prompt, or '' if disabled.

    Schema:
        {
            "enabled": bool,         # master switch (default False)
            "depth_level": 1..5,     # 1=expert, 5=full beginner (default 3)
            "substitution": bool,    # swap jargon for plain English
            "glossary": bool,        # narrate jargon then define inline
            "reframe": bool,         # restructure as teaching moment
        }

    The returned block is intended to be appended to the system / base prompt.
    Empty string = no teacher mode active.
    """
    cfg = teacher_cfg or {}
    if not cfg.get("enabled", False):
        return ""

    depth = cfg.get("depth_level", 3)
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        depth = 3
    depth = max(1, min(5, depth))

    lines: list[str] = ["", "TEACHER MODE — adjust narration for the listener:"]

    # Depth → audience label
    audience_by_depth = {
        1: "Audience: senior engineer. Use precise technical vocabulary; do not over-explain.",
        2: "Audience: experienced developer. Use technical terms freely but skip beginner-level explanations.",
        3: "Audience: mixed-experience listener. Prefer plain English where possible; assume some technical background.",
        4: "Audience: novice learner. Avoid technical shorthand. Define terms when introducing them.",
        5: "Audience: complete beginner. Use everyday English. Treat every technical term as needing explanation.",
    }
    lines.append(f"- {audience_by_depth[depth]}")

    if cfg.get("substitution"):
        lines.append(
            "- Substitute jargon with plain English equivalents. "
            "Example: 'Postgres CTE' becomes 'the database query'; "
            "'TypeScript interface' becomes 'the data shape definition'."
        )
    if cfg.get("glossary"):
        lines.append(
            "- When you must use a technical term, define it inline immediately. "
            "Example: 'The CTE — that's a temporary database query — returned NULL.'"
        )
    if cfg.get("reframe"):
        lines.append(
            "- Frame each event as a teaching moment. Begin with phrases like "
            "'What just happened is...', 'This means...', or 'The reason this matters is...'. "
            "Answer the implicit 'why does this matter?' for each significant action."
        )

    return "\n".join(lines)


def merge_teacher_into_prompt(base_prompt: str, teacher_cfg: dict | None) -> str:
    """Append teacher directives to a base prompt. No-op if teacher mode is off."""
    block = teacher_directives(teacher_cfg)
    if not block:
        return base_prompt
    return base_prompt + "\n" + block


DEFAULT_TEACHER_CONFIG: dict = {
    "enabled": False,
    "depth_level": 3,
    "substitution": False,
    "glossary": False,
    "reframe": False,
}
