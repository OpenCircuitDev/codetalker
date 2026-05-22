"""Mode: critical_only — narrate only critical events.

Parses the turn and sends it to the configured LLM provider with a strict
filter prompt. Returns narration ONLY for errors, blockers, completed major
tasks, or sessions needing user input. Everything else returns None (skip
sentinel) so the dispatcher mutes the narration.

Returns None when nothing critical occurred (skip sentinel for "no narration").
Returns a string (max 20 words) when something critical is detected.
"""
from __future__ import annotations

from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.providers.base import LLMProvider
from claude_code_talker.teacher_mode import (
    max_tokens_for,
    merge_teacher_into_prompt,
    teacher_directives,
)


CRITICAL_ONLY_SYSTEM = """\
You filter and narrate ONLY critical moments in a Claude Code turn.

NARRATE FOR THESE TRIGGERS ONLY:
  1. ERROR or exception thrown (code error, runtime failure, crash)
  2. TEST FAILURE or build break
  3. BLOCKER (waiting for human input, decision needed, dependency unmet)
  4. COMPLETED major task the user explicitly asked about (not routine work)

NARRATE NOTHING FOR:
  - Routine progress ("still working", "continuing", "refactoring")
  - File edits, reads, or tool calls (unless they caused an error)
  - Mid-work status or partial results
  - Anything that does not matter for the user's goal right now

CRITICAL WORD LIMIT: 20 words max (vs brief's 35).

SKIP SENTINEL: If nothing critical occurred, output the exact string: [SKIP]
Do NOT output empty string or explanations. Output [SKIP] when silent.

FORMAT: Lead with what the user must care about:
  - "Error in X: {brief description}."
  - "Tests failing — {cause}."
  - "Blocked on {what}: {who or what is needed}."
  - "Completed: {major task}. Ready to {next step}."

VOICE: Direct, urgent. Alert tone — no warmth words. Just the facts.
Speak as if this is the only thing the user is hearing today.

HEDGE & CHECKPOINT: Skip [UNSURE] and [CHECKPOINT] prefixes for this mode.
Output [SKIP] for uncertain inferences. Critical narration must be certain."""


CRITICAL_ONLY_USER_TEMPLATE = """\
PROSE:
{prose}

TOOL ACTIONS:
{actions}

ERRORS (if any):
{errors}

TODOS:
{todos}

CRITICAL FILTER:"""


# Legacy combined template — kept for defensive backward compatibility.
CRITICAL_ONLY_PROMPT_TEMPLATE = CRITICAL_ONLY_SYSTEM + "\n\n" + CRITICAL_ONLY_USER_TEMPLATE


class CriticalOnlyMode(ModeStrategy):
    name = "critical_only"

    def __init__(self, provider: LLMProvider | None):
        self.provider = provider

    def build(self, prose_entries, tool_uses, todos, cfg):
        # Sync wrapper: not used in production (server uses build_async). Tests use it.
        import asyncio
        return asyncio.run(self.build_async(prose_entries, tool_uses, todos, cfg))

    async def build_async(self, prose_entries, tool_uses, todos, cfg):
        payload = self.build_payload(prose_entries, tool_uses, todos)
        user_prompt = CRITICAL_ONLY_USER_TEMPLATE.format(
            prose=payload["prose"] or "(no prose)",
            actions=self._format_actions(payload["actions"]),
            errors=payload["errors"] or "(no errors detected)",
            todos=self._format_todos(payload["todos"]),
        )

        # Teacher mode support (same pattern as brief)
        teacher_cfg = cfg.get("teacher_mode")
        directives = teacher_directives(teacher_cfg)
        system_prompt = CRITICAL_ONLY_SYSTEM + (("\n" + directives) if directives else "")

        # Critical_only uses smaller token budget (strict 20-word limit)
        max_tokens = max_tokens_for(
            teacher_cfg,
            default=int((cfg.get("critical_only") or {}).get("max_tokens", 100))
        )

        if self.provider is None:
            return self._fallback(payload)

        try:
            raw = (await self.provider.complete(user_prompt, max_tokens, system=system_prompt)).strip()
            # Check for the [SKIP] sentinel — return None to signal "no narration"
            if raw == "[SKIP]":
                return None
            # Strip any stray prefixes (defensive)
            from claude_code_talker.narration_log import parse_checkpoint_prefix, parse_hedge_prefix
            cleaned, _ = parse_checkpoint_prefix(raw)
            cleaned, _ = parse_hedge_prefix(cleaned)
            cleaned = cleaned.strip()
            # If the LLM's response cleaned down to empty, treat as [SKIP]
            if not cleaned:
                return None
            return cleaned
        except Exception:
            return self._fallback(payload)

    def build_payload(self, prose_entries, tool_uses, todos):
        actions: dict[str, int] = {}
        for tu in tool_uses or []:
            name = tu.get("name", "?")
            actions[name] = actions.get(name, 0) + 1

        # Try to extract error indicators from prose
        errors = []
        if prose_entries:
            for entry in prose_entries:
                entry_lower = entry.lower()
                if any(word in entry_lower for word in ["error", "exception", "fail", "crash", "traceback", "stderr"]):
                    errors.append(entry)

        todos = todos or []
        return {
            "prose": "\n\n".join(prose_entries or []),
            "actions": actions,
            "errors": errors,
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
        """Deterministic skip or minimal alert if LLM unavailable."""
        # If there are errors in the payload, emit a minimal alert even without LLM
        if payload["errors"]:
            error_summary = payload["errors"][0][:80]
            return f"Error: {error_summary}"
        # Otherwise, signal skip
        return None
