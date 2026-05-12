"""LLM-generated persona pool for evaluating teacher-mode narrations."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


REQUIRED_PERSONA_FIELDS = (
    "name", "role", "primary_lens", "comfort_with_jargon", "what_they_care_about",
)
PERSONA_COUNT = 5


@dataclass
class Persona:
    name: str
    role: str
    primary_lens: str
    comfort_with_jargon: int  # 1 = jargon-allergic, 5 = jargon-fluent
    what_they_care_about: str


def validate_personas(raw_list: list[dict]) -> list[Persona]:
    """Coerce a list of dicts into validated Persona instances.

    Raises ValueError on the wrong count or any missing required field.
    Clamps comfort_with_jargon to 1-5.
    """
    if not isinstance(raw_list, list) or len(raw_list) != PERSONA_COUNT:
        raise ValueError(f"persona list must have exactly 5 entries, got {len(raw_list) if isinstance(raw_list, list) else type(raw_list).__name__}")
    out: list[Persona] = []
    for i, raw in enumerate(raw_list):
        if not isinstance(raw, dict):
            raise ValueError(f"persona {i} is not a dict")
        missing = [f for f in REQUIRED_PERSONA_FIELDS if f not in raw]
        if missing:
            raise ValueError(f"persona {i} missing fields: {missing}")
        try:
            comfort = int(raw["comfort_with_jargon"])
        except (TypeError, ValueError):
            comfort = 3
        comfort = max(1, min(5, comfort))
        out.append(Persona(
            name=str(raw["name"]),
            role=str(raw["role"]),
            primary_lens=str(raw["primary_lens"]),
            comfort_with_jargon=comfort,
            what_they_care_about=str(raw["what_they_care_about"]),
        ))
    return out


def build_generation_prompt() -> str:
    """Return the prompt used to ask an LLM to produce 5 diverse VIBE-DEVELOPER personas.

    Vibe coding (term popularized by Karpathy 2025) = programming primarily by
    chatting with an LLM in tools like Claude Code / Cursor / Windsurf, with
    light human steering rather than line-by-line review. Codetalker exists
    primarily for these users — they're often listening to narrations while
    multitasking, so getting the audio right MATTERS. Personas must reflect
    the real range of vibe developers (skill / role / what they're building /
    how much they review code).
    """
    return """\
Generate exactly 5 diverse English-native VIBE DEVELOPER personas for evaluating
audio narrations from codetalker, a tool that narrates Claude Code sessions
out loud while users work.

A "vibe developer" / "vibe coder" is someone whose primary programming workflow
is chatting with an AI assistant (Claude Code, Cursor, Windsurf, etc.), lightly
steering it, often running multiple AI sessions in parallel. They range from
non-CS founders building their first SaaS to senior engineers using AI to
accelerate routine work. What unifies them: they trust the AI to do most of
the typing and they're frequently NOT looking at the code while it's being
written — exactly when codetalker's audio narration matters most.

CRITICAL — the 5 personas MUST span TWO independent axes:

  AXIS A — Vibe-coding experience:
    fresh-to-AI (first week with Claude Code / Cursor)  →  power user (lives in
    AI tooling, runs multiple agent sessions in parallel daily)

  AXIS B — Domain / coding expertise (in whatever stack they're working in):
    novice (first language, no formal CS) → expert (staff/principal in their
    field)

These are INDEPENDENT — a senior C++ game dev can be brand-new to vibe coding;
an indie founder can be a 2-year vibe-coding veteran but still learning Python.
The 5 personas should hit a deliberate spread across this 2x2:

  1. NEW VIBE × NEW DOMAIN — first month using any AI tool, also first month
     of programming (e.g. designer using Claude Code to build their first web
     page from scratch). Highest jargon-allergy. Wants WHAT a thing IS, not
     just that it happened.

  2. VETERAN VIBE × NEW DOMAIN — power AI-tool user, but learning a new
     stack (e.g. ex-frontend dev who's been vibe-coding for 18 months, now
     teaching themselves backend in Python with codetalker narrating). Knows
     how to converse with the AI; fuzzy on the language details.

  3. NEW VIBE × VETERAN DOMAIN — senior engineer in their stack, just started
     using Claude Code last week (e.g. 12-yr Java backend dev trying agentic
     dev for the first time). Knows the code cold; suspicious of the AI;
     wants confirmation Claude didn't break anything.

  4. MID VIBE × MID DOMAIN — the "average codetalker user". 6 months of vibe
     coding, mid-level engineer. Runs 2-3 sessions in parallel. Wants "which
     session needs my attention right now" — fast, terse, factual.

  5. POWER VIBE × EXPERT DOMAIN — staff engineer who's been vibe-coding for
     2+ years. Trusts the AI on most edits; reviews only critical paths.
     Wants raw facts, no hand-holding ("did it work, what changed, what's
     next, what does it cost me to keep going").

Then vary the role (indie founder / engineer / designer-who-codes / game dev /
devops / data scientist / non-CS researcher), what they're building (SaaS /
game / CLI tool / data pipeline / mobile app / extension), and when they
listen to codetalker (always / only when away from screen / only during
long-running tasks / parallel-session monitor). Mix these across the spectrum
— don't put the founder at every spot.

Each persona MUST have these fields:
- name (string, first name only)
- role (string, e.g. "Indie SaaS founder, no CS background, building Python web app")
- primary_lens (string, when/how they consume codetalker narrations)
- comfort_with_jargon (integer 1-5; 1=non-CS/jargon-allergic, 5=staff-engineer-fluent)
- what_they_care_about (string, one short sentence describing what they MOST
  want to hear from codetalker — e.g. "did it work and what changed at a high
  level" vs "exact files touched and any errors")

Return ONLY a JSON array of 5 objects. No prose, no markdown fences."""


def parse_personas_response(raw_response: str) -> list[Persona]:
    """Parse the LLM's response into validated Personas.

    Tolerates:
    - ``` / ```json fences
    - leading/trailing whitespace
    - leading commentary before the JSON array
    - trailing commentary after the JSON array (common when the LLM
      explains its choices after the structured output)

    Raises ValueError if the result isn't 5 valid personas.
    """
    text = (raw_response or "").strip()
    if not text:
        raise ValueError(
            "persona response is empty (LLM returned no content — check provider + max_tokens)"
        )
    # Strip optional markdown code fence around the whole response.
    fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.+?)\n?```\s*$", re.DOTALL)
    m = fence_pattern.match(text)
    if m:
        text = m.group(1).strip()
    # Lenient extraction: pull from the first `[` to the last `]` so any
    # surrounding prose ("Here are the personas:" / "Hope these help!")
    # gets stripped before json.loads. Same trick we use for the
    # generate-character endpoint's draft parser.
    first = text.find("[")
    last = text.rfind("]")
    if first != -1 and last > first:
        text = text[first : last + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"persona response is not valid JSON: {e}; raw={raw_response[:200]!r}"
        ) from e
    return validate_personas(data)
