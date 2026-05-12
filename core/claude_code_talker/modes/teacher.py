"""Teacher mode: Brief-shaped narration with teacher directives always applied.

Teacher mode is exposed as a peer of brief/direct/live/trigger in the Android
mode picker (CCT-32 Task A.3, expanded 2026-05-11). Architecturally it builds
on BriefMode (2-4 sentence shape, LLM-driven, deterministic fallback) and
guarantees the teacher_mode prompt-layer fires whether or not the per-session
overlay enabled it explicitly. Per-session teacher_mode keys still win — this
class only fills in defaults when teacher_mode is absent or off.

User-locked spec reference: ``teacher_mode.DEFAULT_TEACHER_CONFIG`` (2026-05-03).
"""
from __future__ import annotations

from claude_code_talker.modes.brief import BriefMode
from claude_code_talker.providers.base import LLMProvider
from claude_code_talker.teacher_mode import DEFAULT_TEACHER_CONFIG


class TeacherMode(BriefMode):
    name = "teacher"

    def __init__(self, provider: LLMProvider | None):
        super().__init__(provider=provider)

    async def build_async(self, prose_entries, tool_uses, todos, cfg):
        cfg_with_teacher = self._ensure_teacher_enabled(cfg)
        return await super().build_async(prose_entries, tool_uses, todos, cfg_with_teacher)

    @staticmethod
    def _ensure_teacher_enabled(cfg: dict) -> dict:
        """Return a cfg copy with teacher_mode.enabled=True, preserving any
        per-session knobs the user already set. If teacher_mode is missing
        entirely, fall back to DEFAULT_TEACHER_CONFIG.
        """
        merged = dict(cfg or {})
        existing = merged.get("teacher_mode")
        if not existing:
            merged["teacher_mode"] = dict(DEFAULT_TEACHER_CONFIG)
        else:
            patched = dict(existing)
            patched.setdefault("enabled", True)
            if not patched.get("enabled", True):
                patched["enabled"] = True
            for key, default_value in DEFAULT_TEACHER_CONFIG.items():
                patched.setdefault(key, default_value)
            merged["teacher_mode"] = patched
        return merged
