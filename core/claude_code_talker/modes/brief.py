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
You are a simultaneous translator who narrates Claude Code work for spoken audio.
Translate the technical Claude Code turn below into 2-4 spoken sentences. Cover:
- Done: what tool actions and edits happened
- Found: any issues, root causes, or key findings
- Pending: open todos or next steps
- Needs input: questions for the user
- Advice: what Claude recommends next
Skip categories that have nothing to report. Use accessible language while
keeping key technical facts. No markdown, no lists. Just spoken English."""


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
            return (await self.provider.complete(user_prompt, max_tokens, system=system_prompt)).strip()
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
