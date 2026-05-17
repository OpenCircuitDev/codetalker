"""
SessionView — the wire-format projection of Session.

Where `Session` (session.py) is the storage shape — what SessionStore
persists and SessionStore.get() returns — `SessionView` is the
per-listener projection that both `/api/sessions` (webui) and
`/api/companion/sessions` (Pro Android) emit. The fields are a
superset of `Session` plus three computed values:

  * `is_live` — does any signal (in-memory SessionState OR fresh
    transcript mtime) say this session is currently open?

  * `is_companion_active` — is this session currently the one a
    paired companion device is listening to? Per-listener: the same
    daemon state can produce two different SessionView objects for
    two different companions.

  * `audio_misaligned` — is `phone` or `glasses` configured but no
    audio_hub subscriber listening? Drives the "configured but not
    receiving" badge on both surfaces.

This is the model the Phase 5 codegen step uses to emit TypeScript
and Kotlin types. After Phase 3 lands, every list-endpoint handler
returns `list[SessionView]` (validated by Pydantic on the way out)
and no field can drift between webui + Pro without changing this
single file.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .character import CharacterRef
from .enums import AudioOutput, Cadence, SpeakingMode


class SessionView(BaseModel):
    """
    Per-listener wire projection of a Session.

    Constructed via views.build_session_view(state, sid, ...). Both
    REST handlers serialize a list of these. The shape is contract:
    adding a field requires editing this schema first, regenerating
    client types, and updating both list handlers (Phase 5 enforces
    this via CI).
    """

    # ------------------------------------------------------------------
    # Identity — what is this session.
    # ------------------------------------------------------------------

    session_id: str = Field(description="Stable UUID from Claude Code.")
    display_name: str = Field(
        description=(
            "Resolved display name. Priority: persistent override > "
            "CC /title custom > VS Code panel label > slug-derived > "
            "catalog title > project_slug fallback."
        ),
    )
    cwd: str = Field(
        default="",
        description="Live cwd if available, else catalog-cached. Empty string when neither known.",
    )
    project_slug: str = Field(
        default="",
        description="Catalog-derived project slug. Empty for live-only sessions not yet cataloged.",
    )
    project_dir: str = Field(
        default="",
        description="Claude Code's project directory name. Empty when transcript path unknown.",
    )
    workspace_group: Optional[str] = Field(
        default=None,
        description="Persistent override > derive_from_display_name. None = Ungrouped.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Catalog auto-title (first user prompt snippet). Distinct from display_name.",
    )

    # ------------------------------------------------------------------
    # Speaking behavior.
    # ------------------------------------------------------------------

    active_mode: Optional[SpeakingMode] = Field(
        default=None,
        description="Resolved per-session mode. None = inherit daemon default.",
    )
    cadence: Optional[Cadence] = Field(
        default=None,
        description="Only meaningful when active_mode == 'live'. None = inherit master.",
    )
    enabled: bool = Field(
        default=True,
        description="Per-session mute. False = no TTS regardless of master.",
    )
    auto_mode_enabled: bool = Field(
        default=False,
        description="When True, daemon auto-flips active_mode based on interaction recency.",
    )

    # ------------------------------------------------------------------
    # Audio routing.
    # ------------------------------------------------------------------

    audio_outputs: Optional[List[AudioOutput]] = Field(
        default=None,
        description=(
            "Configured sink set. None = fall back to fleet default. "
            "[] = explicit silence everywhere."
        ),
    )

    # ------------------------------------------------------------------
    # Voice + character.
    # ------------------------------------------------------------------

    attached_profile: Optional[str] = Field(
        default=None,
        description="Profile name (preset config bundle) attached to this session.",
    )
    attached_character: Optional[CharacterRef] = Field(
        default=None,
        description=(
            "Resolved character record (voice_ref, mesh_path, persona, "
            "emotive_states). None = no character attached."
        ),
    )

    # ------------------------------------------------------------------
    # Liveness + transient flags.
    # ------------------------------------------------------------------

    is_live: bool = Field(
        default=False,
        description=(
            "Computed: in-memory SessionState present OR transcript "
            "mtime within TRANSCRIPT_LIVE_WINDOW_SEC."
        ),
    )
    is_speaking: bool = Field(
        default=False,
        description="Transient: True while audio worker plays this session's WAV.",
    )
    is_companion_active: bool = Field(
        default=False,
        description=(
            "Per-listener: this session is in companion_active_sessions "
            "for the requesting companion. Always False on webui endpoint."
        ),
    )
    audio_misaligned: bool = Field(
        default=False,
        description=(
            "Computed: phone/glasses in audio_outputs but no audio_hub "
            "subscriber. 'Configured but not receiving' badge driver."
        ),
    )
    has_persistent_settings: bool = Field(
        default=False,
        description="True iff a persistent overlay file exists on disk.",
    )

    # ------------------------------------------------------------------
    # Timestamps.
    # ------------------------------------------------------------------

    last_modified: float = Field(
        default=0.0,
        description=(
            "Epoch seconds. Catalog transcript mtime, OR live "
            "last_hook_at — whichever is larger."
        ),
    )
    last_hook_at: float = Field(
        default=0.0,
        description="Epoch seconds of last CC hook fire. 0 = no hook this run.",
    )
    last_user_interaction_at: float = Field(
        default=0.0,
        description=(
            "Epoch seconds of last UserPromptSubmit / buddy inject. "
            "Drives the LISTENING lifecycle state."
        ),
    )

    # ------------------------------------------------------------------
    # User preferences.
    # ------------------------------------------------------------------

    pinned: bool = Field(
        default=False,
        description="Pin-to-top within the workspace group.",
    )

    model_config = {
        # SessionView is the wire format — extra fields would silently
        # leak past Pydantic validation. Keep it forbid.
        "extra": "forbid",
    }
