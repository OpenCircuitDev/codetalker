"""Mode B: turn-end brief.

Parses the turn into a structured payload, sends it to the configured LLM
provider with a translation-prompt template, returns the LLM's brief. Falls
back to a deterministic structured speech if the provider fails.
"""
from __future__ import annotations

from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.providers.base import LLMProvider
from claude_code_talker.teacher_mode import (
    max_tokens_for,
    merge_teacher_into_prompt,
    teacher_directives,
)


# 2026-05-11 — split into system+user blocks so Anthropic provider can cache
# the stable instruction prefix (cache_control: ephemeral, see
# providers/anthropic.py). Below the per-model cache threshold (Haiku: 2048
# tokens; Sonnet/Opus: 1024) the cache attach is a no-op but stays semantically
# correct. When teacher_directives are appended to BRIEF_SYSTEM, the combined
# system block grows toward the threshold and caching kicks in.
BRIEF_SYSTEM = """\
You narrate a one-breath spoken brief at the end of a Claude Code turn.
The user is away from the screen and needs the smallest possible
picture of where they are.

BRIEFNESS IS PRIMARY.
Default output: ONE SENTENCE, 15-22 words. Use a second sentence ONLY
when the user has a decision waiting on them (a question Claude is
asking, or a divergence that needs their input). NEVER a third. Hard
cap: 45 words.

Lead with the RESULT, not the journey. Past tense for what landed.
Not "Claude was working on the rebase and..." — "Three PRs green; two
still running CI."

CHOOSE EXACTLY ONE OF THESE TO REPORT:
  1. CLAUDE IS ASKING THE USER → restate the question + 2 options +
     one-word recommendation. Two sentences. ("Should the new role
     check be opt-in or default-on? Opt-in is safer; default-on
     matches the rest of the system. Lean default-on.")
  2. DIVERGENCE from the plan → flag it. ("Hit the shared-config
     conflict and resolved favoring the new side.")
  3. WHAT'S NOW POSSIBLE / BLOCKED → state it. ("Auth refactor done.
     Wiring next.")
  4. KEY FINDING → if a real insight surfaced. ("All four crashes
     traced to the same null-check.")
  5. WHAT'S NEXT if Claude is mid-task and continuing autonomously.
     ("Schema migration next.")

THE ACTIVE-GOAL CLAUSE IS CONDITIONAL.
Append "...on your X goal" ONLY when:
  - The turn ENDED the user's named goal (worth marking the close), OR
  - The turn meaningfully advanced or threatened it.
Skip it for routine turns. Repeating the goal at every wrap is filler.

NEVER DO:
- Speak file paths or absolute file names. Only the file's function.
- Enumerate every tool call. One beat for the whole batch.
- Pad with "Claude is working on...", "still processing", "standing
  by", "in progress".
- Speculate about future intent beyond the one "what's next" sentence.
- Speak ISO timestamps. Relative time only.
- Use parenthetical stage directions or meta-comments.

VOICE: A colleague handing off the turn. Curt but warm. Plain spoken
English.

HEDGE WHEN UNCERTAIN.
If your brief is summarizing INFERENCE (you're guessing at intent
from incomplete events) rather than DIRECT OBSERVATION (a file
edit landed, a test passed, a command ran), prefix your output
with [UNSURE] followed by a single space. Examples of uncertain:
  - You're inferring what Claude is "about to" do from prep-work
    tool calls that haven't committed to an action yet.
  - The assistant prose is hedging itself ("I think", "this might",
    "let me see if") and you're reflecting that.
  - The events show a result but the prior decision-point is
    ambiguous — you're not sure whether this is the OUTCOME the
    user wanted or a sidequest.
Direct observations never get [UNSURE]."""


BRIEF_USER_TEMPLATE = """\
PROSE:
{prose}

TOOL ACTIONS:
{actions}

TODOS:
{todos}

BRIEF:"""


# Legacy combined template — kept so anything that imports the symbol does not
# break, and as the prompt used when system+user blocks aren't supported by the
# provider (none today, but defensive).
BRIEF_PROMPT_TEMPLATE = BRIEF_SYSTEM + "\n\n" + BRIEF_USER_TEMPLATE


class BriefMode(ModeStrategy):
    name = "brief"

    def __init__(self, provider: LLMProvider | None):
        self.provider = provider

    def build(self, prose_entries, tool_uses, todos, cfg):
        # Sync wrapper: not used in production (server uses build_async). Tests use it.
        import asyncio
        return asyncio.run(self.build_async(prose_entries, tool_uses, todos, cfg))

    async def build_async(self, prose_entries, tool_uses, todos, cfg):
        payload = self.build_payload(prose_entries, tool_uses, todos)
        user_prompt = BRIEF_USER_TEMPLATE.format(
            prose=payload["prose"] or "(no prose)",
            actions=self._format_actions(payload["actions"]),
            todos=self._format_todos(payload["todos"]),
        )
        # Stable instruction prefix → system block (cacheable on Anthropic).
        # Teacher directives extend the system block when teacher_mode is on,
        # which (a) keeps the variable user-prompt minimal so cache hits are
        # more frequent and (b) bulks the system block closer to the model's
        # cache-threshold (Haiku: 2048; Sonnet/Opus: 1024).
        teacher_cfg = cfg.get("teacher_mode")
        directives = teacher_directives(teacher_cfg)
        system_prompt = BRIEF_SYSTEM + (("\n" + directives) if directives else "")
        # Teacher.verbosity overrides the brief.max_tokens default when on.
        # Brief mode default is 200; teacher.expanded bumps to 320.
        max_tokens = max_tokens_for(teacher_cfg, default=int((cfg.get("brief") or {}).get("max_tokens", 200)))
        if self.provider is None:
            return self._fallback(payload)
        try:
            raw = (await self.provider.complete(user_prompt, max_tokens, system=system_prompt)).strip()
            # 2026-05-21 — strip the [UNSURE] hedge prefix before returning so
            # TTS doesn't speak "UNSURE" out loud. confidence is captured but
            # not yet plumbed through the dispatch chain (v2: pass to
            # NarrationEntry.confidence + render a hedge badge in the webui).
            from claude_code_talker.narration_log import parse_hedge_prefix
            cleaned, _confidence = parse_hedge_prefix(raw)
            return cleaned
        except Exception:
            return self._fallback(payload)

    def build_payload(self, prose_entries, tool_uses, todos):
        actions: dict[str, int] = {}
        for tu in tool_uses or []:
            name = tu.get("name", "?")
            actions[name] = actions.get(name, 0) + 1

        todos = todos or []
        return {
            "prose": "\n\n".join(prose_entries or []),
            "actions": actions,
            "todos": {
                "in_progress": [t.get("content", "") for t in todos if t.get("status") == "in_progress"],
                "pending": [t.get("content", "") for t in todos if t.get("status") == "pending"],
                "completed_count": sum(1 for t in todos if t.get("status") == "completed"),
            },
        }

    def _format_actions(self, actions):
        if not actions:
            return "(none)"
        return ", ".join(f"{name}:{count}" for name, count in actions.items())

    def _format_todos(self, todos):
        parts = []
        if todos["in_progress"]:
            parts.append(f"in_progress={todos['in_progress']}")
        if todos["pending"]:
            parts.append(f"pending={todos['pending']}")
        if todos["completed_count"]:
            parts.append(f"completed_count={todos['completed_count']}")
        return ", ".join(parts) if parts else "(none)"

    def _fallback(self, payload):
        """Deterministic structured speech if LLM unavailable."""
        bits = []
        if payload["prose"]:
            bits.append(payload["prose"][:400])
        if payload["actions"]:
            verbs = []
            for name, count in payload["actions"].items():
                if name == "Read":
                    verbs.append(f"read {count} file{'s' if count != 1 else ''}")
                elif name == "Edit":
                    verbs.append(f"edited {count} file{'s' if count != 1 else ''}")
                elif name == "Write":
                    verbs.append(f"wrote {count} file{'s' if count != 1 else ''}")
                else:
                    verbs.append(f"{count} {name}")
            bits.append("Tool actions: " + ", ".join(verbs) + ".")
        if payload["todos"]["in_progress"]:
            bits.append("In progress: " + ", ".join(payload["todos"]["in_progress"]) + ".")
        if payload["todos"]["pending"]:
            bits.append("Coming up: " + ", ".join(payload["todos"]["pending"]) + ".")
        return " ".join(bits)
