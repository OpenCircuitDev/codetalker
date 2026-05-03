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


VERBOSITY_LEVELS = ("concise", "standard", "expanded")
GRANULARITY_LEVELS = ("combined", "per-file")

# Max-tokens budget per verbosity. Maps to LLMProvider.complete(max_tokens=...)
# so the model knows how much room it has. Concise stays under one ~30-word
# sentence; standard is 2-3 sentences; expanded is a short paragraph.
VERBOSITY_TOKEN_BUDGET = {
    "concise": 60,
    "standard": 140,
    "expanded": 320,
}


def teacher_directives(teacher_cfg: dict | None) -> str:
    """Return the directive block to inject into a prompt, or '' if disabled.

    Schema:
        {
            "enabled": bool,           # master switch (default True)
            "depth_level": 1..5,       # 1=expert, 5=full beginner (default 3)
            "substitution": bool,      # swap jargon for plain English
            "glossary": bool,          # narrate jargon then define inline
            "reframe": bool,           # restructure as teaching moment
            "verbosity": str,          # "concise" / "standard" / "expanded"
            "granularity": str,        # "combined" / "per-file"
        }

    The returned block is intended to be appended to the system / base prompt.
    Empty string = no teacher mode active.
    """
    # IMPORTANT: when teacher_cfg is explicitly None (caller said "not set"),
    # we treat that as "no teacher mode". Empty dict {} on the other hand
    # gets the default applied, which means enabled=True and the block fires.
    # This split exists because hot paths (LiveMode etc.) pass cfg.get("teacher_mode")
    # which can return None — and we don't want narration to suddenly start
    # using teacher mode for sessions that never opted in.
    if teacher_cfg is None:
        return ""
    cfg = teacher_cfg
    if not cfg.get("enabled", True):
        return ""

    depth = cfg.get("depth_level", 3)
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        depth = 3
    depth = max(1, min(5, depth))

    verbosity = cfg.get("verbosity", "concise")
    if verbosity not in VERBOSITY_LEVELS:
        verbosity = "concise"
    granularity = cfg.get("granularity", "combined")
    if granularity not in GRANULARITY_LEVELS:
        granularity = "combined"

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

    # Verbosity → length cap
    verbosity_directive = {
        "concise": "- LENGTH: one short sentence (≤30 words). Maximum compression.",
        "standard": "- LENGTH: 2-3 sentences (≤70 words). Room for one supporting clause per action.",
        "expanded": "- LENGTH: short paragraph (≤150 words). Take the space to explain the WHY at the file level and connect actions back to the user's most recent prompt.",
    }
    lines.append(verbosity_directive[verbosity])

    # Granularity → how to handle multiple file edits
    granularity_directive = {
        "combined": "- GRANULARITY: combined. Group related file edits into one explanation (\"Across auth.py and tests/, Claude is wiring X\").",
        "per-file": "- GRANULARITY: per-file. Mention each distinct file edit in its own clause/sentence. Explain what's changing in each file and why.",
    }
    lines.append(granularity_directive[granularity])

    # Anchor to the user's prompt as the WHY (always when teacher is on).
    lines.append(
        "- ANCHOR TO PROMPT: tie what's happening back to the user's most recent "
        "USER_PROMPT entry in the events. The user's prompt is the WHY behind "
        "every subsequent tool action."
    )

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


def max_tokens_for(teacher_cfg: dict | None, default: int = 150) -> int:
    """Return the LLM max_tokens budget given the teacher.verbosity setting.

    None or ``enabled=False`` returns ``default``. Empty dict OR enabled=True
    with no explicit verbosity defaults to ``concise``.
    """
    if teacher_cfg is None:
        return default
    if not teacher_cfg.get("enabled", True):
        return default
    verbosity = teacher_cfg.get("verbosity", "concise")
    return VERBOSITY_TOKEN_BUDGET.get(verbosity, default)


DEFAULT_TEACHER_CONFIG: dict = {
    "enabled": True,
    "depth_level": 3,
    "substitution": False,
    "glossary": False,
    "reframe": False,
    "verbosity": "standard",  # Was 'concise'; user wants more descriptive default
    "granularity": "combined",
}
