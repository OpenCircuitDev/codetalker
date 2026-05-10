"""Tag library + SKILL.md composition for Phase 14.5 trigger mode."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Tag:
    id: str                    # normalized e.g. "audible_summary"
    display_name: str          # "Audible Summary"
    enabled: bool = False
    editor_mode: str = "structured"    # "structured" | "freeform"
    when_to_trigger: str = ""
    format_template: str = ""
    example: str = ""
    freeform_text: str = ""    # populated only when editor_mode == "freeform"
    # Phase 26: per-tag markup treatment overrides applied to the block body
    # before TTS. Shape: {"<form>": {"kind": "...", "params": {...}}}.
    markup_overrides: dict = field(default_factory=dict)


# Starter tags installed on first run if cfg has no triggers.tags.
# (Originally 5; now 10 with the plan-mode / subagent / skill / permission
# tags. Tests should assert >= 5 with the original IDs present.)
STARTER_TAGS: list[Tag] = [
    Tag(
        id="audible_summary",
        display_name="Audible Summary",
        enabled=True,
        editor_mode="structured",
        when_to_trigger="you've completed a meaningful step and are pausing for input or showing a result",
        format_template="one paragraph, ≤60 words, plain audible English, present or past tense",
        example="I'm restarting PIE clean and slowing time dilation to stretch the 6-second cycle to 30 seconds.",
    ),
    Tag(
        id="audible_synopsis",
        display_name="Audible Synopsis",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="the user asks for a recap or you want to surface the session arc so far",
        format_template="one paragraph, ≤80 words, present perfect tense, what's been investigated/decided/built",
        example="We've narrowed the bug to the singleton race in LiveMode, fixed it via per-session state, and added a regression test.",
    ),
    Tag(
        id="audible_briefs",
        display_name="Audible Briefs",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="you're wrapping up a turn — what got done in this batch",
        format_template="one paragraph, ≤60 words, past tense",
        example="Two commits landed. Tests are green. Daemon needs a bounce to load the changes.",
    ),
    Tag(
        id="audible_listings",
        display_name="Audible Listings",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="you're enumerating steps, options, or checklist items the user should hear",
        format_template="numbered or bulleted list of short items, ≤6 items, ≤20 words each",
        example="One: extract the audio. Two: detect the face. Three: post to the avatar service.",
    ),
    Tag(
        id="audible_details",
        display_name="Audible Details",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="the user has signaled they want the deep technical exposition narrated, not just the summary",
        format_template="up to three paragraphs, can include technical specifics; still no URLs, paths, or long numerals",
        example="The reason this works is that the parser auto-recognizes any header beginning with Audible, so adding a new tag in the UI takes effect immediately without a parser update or daemon bounce.",
    ),
    Tag(
        id="audible_plan_entry",
        display_name="Audible Plan Entry",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="you've just entered plan mode (created a plan file or are about to call ExitPlanMode) and want to surface the high-level plan for the listener",
        format_template="one paragraph, ≤80 words, present tense, what the plan covers and the first concrete step",
        example="The plan covers a phased rollout starting with the trigger pack, then the dashboard, then live narration. First step is adding five Claude-Code-aware starter tags.",
    ),
    Tag(
        id="audible_subagent_done",
        display_name="Audible Subagent Result",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="a Task subagent has returned a result you're about to summarize for the user — narrate the outcome, not the process",
        format_template="one paragraph, ≤60 words, past tense, the result the subagent produced and what you'll do with it",
        example="The exploration agent found two existing utilities that already handle this case. I'll wire them in instead of adding new code.",
    ),
    Tag(
        id="audible_todo_advance",
        display_name="Audible Todos Update",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="TodoWrite advanced a meaningful task to in_progress or completed — narrate the move, not the full list",
        format_template="one short sentence, ≤25 words, past tense for completed or present continuous for starting",
        example="Marking the trigger pack task complete and starting on the dashboard scaffold.",
    ),
    Tag(
        id="audible_skill_invoked",
        display_name="Audible Skill Invoked",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="you've activated a skill via the Skill tool that the listener should know about — name it and what it'll change",
        format_template="one sentence, ≤30 words, present tense, naming the skill and the effect",
        example="Loading the brainstorming skill so we can scope the design properly before any code lands.",
    ),
    Tag(
        id="audible_permission_request",
        display_name="Audible Permission Request",
        enabled=False,
        editor_mode="structured",
        when_to_trigger="a tool permission prompt is about to fire and the listener may need to grant or deny — narrate what's being requested and why",
        format_template="one sentence, ≤30 words, present tense, what action is requested and the purpose",
        example="Asking permission to push to the public repository so the marketplace install path becomes live.",
    ),
]


_TEACHER_PROMPTS = {
    "plain":     "Write narrations in plain English. Avoid jargon. If a technical term is unavoidable, define it inline.",
    "standard":  "Write narrations using normal technical English. Don't over-explain common dev terms.",
    "technical": "Write narrations using full technical vocabulary. Precision over accessibility.",
}


class TagLibrary:
    """In-memory tag store. Persisted by the caller into cfg-overlay.yaml."""

    def __init__(self):
        self._tags: dict[str, Tag] = {}

    def add(self, tag: Tag) -> None:
        self._tags[tag.id] = tag

    def get(self, tag_id: str) -> Tag | None:
        return self._tags.get(tag_id)

    def delete(self, tag_id: str) -> bool:
        return self._tags.pop(tag_id, None) is not None

    def update(self, tag_id: str, **changes) -> Tag | None:
        t = self._tags.get(tag_id)
        if t is None:
            return None
        for k, v in changes.items():
            if hasattr(t, k):
                setattr(t, k, v)
        return t

    def list(self) -> list[Tag]:
        return list(self._tags.values())

    def enabled_ids(self) -> set[str]:
        return {t.id for t in self._tags.values() if t.enabled}

    def bootstrap_starters(self) -> None:
        """If empty, populate with the starter tags (`STARTER_TAGS`). Idempotent."""
        if self._tags:
            return
        for t in STARTER_TAGS:
            self._tags[t.id] = Tag(**asdict(t))  # copy

    @classmethod
    def from_cfg(cls, cfg_section: dict | None) -> "TagLibrary":
        lib = cls()
        if not cfg_section:
            return lib
        for tag_id, raw in cfg_section.items():
            if not isinstance(raw, dict):
                continue
            try:
                lib._tags[tag_id] = Tag(id=tag_id, **{k: v for k, v in raw.items() if k != "id"})
            except TypeError:
                continue
        return lib

    def to_cfg(self) -> dict:
        return {tid: {k: v for k, v in asdict(t).items() if k != "id"}
                for tid, t in self._tags.items()}


def compose_skill_static_shell() -> str:
    """Frontmatter + intro paragraph. Static, plugin-shipped portion of SKILL.md.

    The dynamic body (trigger blocks + style guidance) comes from
    `compose_skill_body()` and is served by `/api/triggers/skill-body` so the
    plugin's SKILL.md can pull live state at every activation.
    """
    lines: list[str] = []
    lines.append("---")
    lines.append("name: codetalker-narration")
    lines.append(
        "description: When the user has codetalker running, write tagged narration "
        "blocks for the user-selected trigger types so codetalker can speak them "
        "verbatim through TTS."
    )
    lines.append("---")
    lines.append("")
    lines.append("# Codetalker Narration")
    lines.append("")
    lines.append(
        "The user is listening to your work via codetalker (a TTS narrator daemon). "
        "For specific moments listed below, write a markdown block with the exact "
        "header form shown. Codetalker extracts the content beneath each header "
        "and speaks it verbatim. Use this to keep the listener informed without "
        "forcing them to read the chat."
    )
    lines.append("")
    return "\n".join(lines)


def compose_skill_body(
    lib: TagLibrary,
    *,
    teacher_level: str = "standard",
    persona: str = "methodical",
) -> str:
    """Dynamic body: trigger blocks + style guidance. Depends on cfg.

    Served by `/api/triggers/skill-body` and injected into the plugin's
    SKILL.md at activation time.
    """
    teacher_directive = _TEACHER_PROMPTS.get(teacher_level, _TEACHER_PROMPTS["standard"])
    enabled = [t for t in lib.list() if t.enabled]

    lines: list[str] = []
    if not enabled:
        lines.append("(No tags enabled — codetalker won't speak anything until at least one tag is enabled in the Web UI.)")
        return "\n".join(lines)

    lines.append("## Trigger blocks")
    lines.append("")
    for t in enabled:
        lines.append(f"### When to write a `## {t.display_name}` block")
        if t.editor_mode == "freeform" and t.freeform_text.strip():
            lines.append(t.freeform_text.strip())
        else:
            if t.when_to_trigger:
                lines.append(f"Trigger: {t.when_to_trigger}.")
            lines.append("")
            lines.append("Format:")
            lines.append("```")
            lines.append(f"## {t.display_name}")
            lines.append(f"<{t.format_template or 'one paragraph, audio-friendly'}>")
            lines.append("```")
            if t.example:
                lines.append("")
                lines.append(f'Example: "{t.example}"')
        lines.append("")

    lines.append("## Style guidance")
    lines.append("")
    lines.append(f"- {teacher_directive}")
    lines.append("- Each block is one paragraph (or as the format specifies). No code blocks inside narration headers.")
    lines.append(
        "- Don't read aloud URLs, file paths, or long numbers. Describe them: "
        "\"the auth file\" not \"src/auth/login.py\"; \"a long timestamp\" not the raw digits."
    )
    lines.append(f"- Voice persona: {persona}. Match its tone.")
    lines.append("- If multiple narration types apply to the same moment, pick the most specific one. Don't write redundant blocks.")
    lines.append("")

    return "\n".join(lines)


def compose_skill_content(
    lib: TagLibrary,
    *,
    teacher_level: str = "standard",
    persona: str = "methodical",
) -> str:
    """Compose the full SKILL.md content. Used by the legacy non-plugin write path.

    Plugin users get the static shell from `compose_skill_static_shell()` plus
    a live `!`curl /api/triggers/skill-body`` injection, so this full-content
    function is only used when writing `~/.claude/skills/codetalker-narration/`
    directly (the pre-Phase-18 install).
    """
    return compose_skill_static_shell() + "\n" + compose_skill_body(
        lib, teacher_level=teacher_level, persona=persona,
    )
