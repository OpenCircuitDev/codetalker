"""
Codetalker domain schemas.

This module is the canonical contract for every piece of data that
crosses a process boundary — between the daemon and the webui, the
daemon and the Pro Android app, and the daemon and persistent
storage. The Pydantic models defined here are:

  1. Runtime-validated at every API boundary (daemon returns 400 on
     malformed input, raises on malformed output).

  2. Code-generated into TypeScript types for the webui and Kotlin
     data classes for the Pro app (see Phase 5 of the refactor plan).

  3. The single place to look up "what fields does a Session have?"
     — no more grep across 9 different shapes.

Before adding ANY new field anywhere in the codebase, add it here
first. Then regenerate the client types. The build will fail until
all three surfaces agree.

See docs/refactor-plan-2026-05-16.md for the full architecture.
"""
from __future__ import annotations

# Re-export every public schema so callers do one import:
#     from claude_code_talker.schemas import Session, MasterConfig, ...
from .audio_job import AudibleStatus, AudioJob, StateTransition
from .character import CharacterRef
from .enums import (
    AudibleReason,
    AudioJobState,
    AudioOutput,
    Cadence,
    CharacterPose,
    DeviceType,
    MasterPreset,
    SessionLifecycle,
    SpeakingMode,
    VoiceEngine,
)
from .events import (
    AudioJobStateChanged,
    CharacterPoseChanged,
    Event,
    LifecycleChanged,
    MasterConfigChanged,
    SessionChanged,
    SubscriptionChanged,
)
from .master import BriefsConfig, MasterConfig
from .narration import (
    MARKUP_FORM_KINDS,
    CodeBlocksTreatment,
    MarkupTreatment,
    NarrationConfig,
    PathsHandling,
)
from .patches import MasterConfigPatch, SessionPatch
from .session import Session
from .voice import VoiceConfig

__all__ = [
    # enums
    "AudibleReason",
    "AudioJobState",
    "AudioOutput",
    "Cadence",
    "CharacterPose",
    "DeviceType",
    "MasterPreset",
    "SessionLifecycle",
    "SpeakingMode",
    "VoiceEngine",
    # domain
    "Session",
    "SessionPatch",
    "MasterConfig",
    "MasterConfigPatch",
    "BriefsConfig",
    "VoiceConfig",
    "NarrationConfig",
    "MarkupTreatment",
    "MARKUP_FORM_KINDS",
    "PathsHandling",
    "CodeBlocksTreatment",
    "CharacterRef",
    "AudioJob",
    "AudibleStatus",
    "StateTransition",
    # events
    "Event",
    "SessionChanged",
    "LifecycleChanged",
    "AudioJobStateChanged",
    "MasterConfigChanged",
    "SubscriptionChanged",
    "CharacterPoseChanged",
]
