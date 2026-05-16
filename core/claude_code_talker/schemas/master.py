"""
MasterConfig — global, fleet-wide settings.

Lives in ~/.claude/scripts/tts_config.yaml (per user direction on
2026-05-16: stay file-based). The schema validates the YAML contents
on load and on every PATCH. Daemon writes back the validated form so
the file converges to the schema even if a user hand-edits it.

This replaces the bare state.cfg dict the daemon currently builds via
deep-merge of preset + YAML + cfg-overlay. The dict-based approach
made every cfg.get("enabled") call ambiguous — the value could come
from preset defaults, global config, or cfg-overlay, with no type
safety. After this refactor, the daemon loads YAML → validates into
MasterConfig → stores as state.master_config. Every reader gets a
typed model.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .enums import AudioOutput, MasterPreset
from .voice import VoiceConfig


class BriefsConfig(BaseModel):
    """Sub-toggles for which hook events produce brief narration."""

    user_prompt_enabled: bool = Field(
        default=True,
        description="True = UserPromptSubmit produces a 'You just asked' brief.",
    )
    always_brief_on_stop: bool = Field(
        default=True,
        description="True = even in direct mode, Stop hook emits a synopsis brief.",
    )
    posttool_enabled: bool = Field(
        default=True,
        description="True = PostToolUse hook may emit a brief (significance-gated).",
    )
    notification_enabled: bool = Field(
        default=True,
        description="True = Notification hook is spoken verbatim.",
    )

    model_config = {"extra": "forbid"}


class MasterConfig(BaseModel):
    """
    Global codetalker configuration. The master narration switch lives
    here; per-session overrides cannot override `enabled: False` at the
    master level — when this is False, the entire fleet is silent.

    Edit either via PATCH /api/master or by hand in
    ~/.claude/scripts/tts_config.yaml. The daemon validates on load
    and on every write.
    """

    enabled: bool = Field(
        default=True,
        description=(
            "Master on/off. False silences ALL hook-driven TTS across "
            "every session. This is the gate that was set False for 5 "
            "days during the 2026-05-16 audio outage."
        ),
    )
    preset: MasterPreset = Field(
        default="monitor",
        description=(
            "Top-level defaults bundle. Defined in core/claude_code_talker/"
            "presets.py. monitor is the production default (live mode "
            "with periodic cadence)."
        ),
    )
    voice: VoiceConfig = Field(
        default_factory=VoiceConfig,
        description="Fleet-default voice. Per-session voice overrides this.",
    )
    audio_outputs_default: List[AudioOutput] = Field(
        default_factory=lambda: ["desktop", "phone", "glasses"],
        description=(
            "Fleet default for audio_outputs when a session's overlay "
            "doesn't specify. The current code uses {desktop, phone, "
            "glasses} as the fallback; this captures that explicitly."
        ),
    )
    briefs: BriefsConfig = Field(
        default_factory=BriefsConfig,
        description="Sub-toggles for hook-event narration.",
    )

    model_config = {"extra": "forbid"}
