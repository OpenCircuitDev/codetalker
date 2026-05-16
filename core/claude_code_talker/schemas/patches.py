"""
Partial-update schemas for PATCH endpoints.

A PATCH request carries only the fields the caller wants to change.
Pydantic's `model_construct(**partial)` doesn't enforce required
fields, but we want stronger guarantees: every field that CAN be
patched must be enumerated here. This prevents typos at the client
from accidentally creating extra fields on the server.

When a new Session field is added in session.py, the corresponding
SessionPatch field MUST be added here as Optional. The PR will fail
linting if the two get out of sync (a tooling task for phase 5).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .character import CharacterRef
from .enums import AudioOutput, Cadence, SpeakingMode
from .voice import VoiceConfig


class SessionPatch(BaseModel):
    """
    Partial Session for PATCH /api/sessions/{sid}. All fields
    optional; omitted fields are not changed. Daemon validates input
    against this schema and rejects unknown fields with 400.

    Computed fields (lifecycle, last_*_at, is_speaking via job state)
    are intentionally NOT patchable. Only user-controllable settings
    can be PATCHed; daemon-computed state is read-only.
    """

    display_name: Optional[str] = None
    workspace_group: Optional[str] = None
    active_mode: Optional[SpeakingMode] = None
    cadence: Optional[Cadence] = None
    enabled: Optional[bool] = None
    auto_mode_enabled: Optional[bool] = None
    audio_outputs: Optional[List[AudioOutput]] = None
    voice: Optional[VoiceConfig] = None
    attached_profile: Optional[str] = None
    # Note: attached_character is a CharacterRef OR a character_id string
    # (clients can patch with either; the daemon resolves string IDs to
    # the full record before storage). For now we accept the full record.
    attached_character: Optional[CharacterRef] = None
    pinned: Optional[bool] = None

    model_config = {"extra": "forbid"}


class MasterConfigPatch(BaseModel):
    """
    Partial MasterConfig for PATCH /api/master. Same pattern as
    SessionPatch — all fields optional, unknown fields rejected.

    The 90% common case is patching only `enabled`. The webui status
    bar pill and Pro Sessions header pill both send
    `{"enabled": <bool>}` and nothing else.
    """

    enabled: Optional[bool] = None
    preset: Optional[str] = None
    voice: Optional[VoiceConfig] = None
    audio_outputs_default: Optional[List[AudioOutput]] = None

    model_config = {"extra": "forbid"}
