"""
Character — a narration persona with voice, mesh, and emotive states.

A character bundles together the data the AR/XR HUD needs to render
an avatar that "speaks" the narration. Today the webui shows the
display_name + persona text; the Pro Android app surfaces the same
chip. Phase 7 (post-stabilization) wires the mesh_path into the
glasses Display 6 Compose Presentation.

The schema includes EVERY character field today's daemon knows
about, regardless of whether each client currently renders it. This
prevents the "field exists in webui response but not companion
response" drift that was a Major finding in the 2026-05-16 audit.
"""
from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field

from .enums import CharacterPose


class CharacterRef(BaseModel):
    """
    A character record as embedded in a Session.attached_character or
    returned from /api/characters/{id}. Single shape for both list-
    endpoint embedding and detail-endpoint lookup.

    The mesh_* fields are AR/XR-specific. They're carried in the
    schema today so:
      1. The webui can preview the mesh (already implemented).
      2. The Pro Android character sheet can show "has mesh" badge.
      3. The glasses HUD (phase 7) can render the avatar directly
         without a separate API call.
    """

    id: str = Field(
        description="Stable kebab-case identifier, used in URLs and overlays.",
    )
    display_name: str = Field(
        description="Human-readable name shown in UIs.",
    )
    persona: str = Field(
        default="",
        description=(
            "Brief description of personality / role. Used in triggers.persona "
            "config so the LLM prompts know the speaking voice's identity."
        ),
    )
    voice_ref: str = Field(
        description=(
            "Voice model identifier. Either a Piper voice name (e.g. "
            "'en_US-joe-medium') or a cloned-voice ID (e.g. 'char-aria-v1')."
        ),
    )
    mesh_path: Optional[str] = Field(
        default=None,
        description=(
            "Filesystem path to the GLB/GLTF mesh asset for AR avatar render. "
            "None when no 3D asset is bound. Daemon serves this path via "
            "/api/characters/{id}/mesh for clients that need the bytes."
        ),
    )
    mesh_provider: Optional[str] = Field(
        default=None,
        description=(
            "Which mesh generator produced this asset (meshy, tripo3d, "
            "hyper3d, user-uploaded). Informational; used by the webui "
            "character editor to show provenance."
        ),
    )
    mesh_prompt: Optional[str] = Field(
        default=None,
        description=(
            "The text prompt used to generate the mesh (when AI-generated). "
            "Allows regeneration with edits."
        ),
    )
    emotive_states: Dict[CharacterPose, str] = Field(
        default_factory=dict,
        description=(
            "Per-pose prompt hints that drive avatar animation. Maps pose "
            "names to short text descriptions like 'leans forward, ear "
            "cupped' for 'listening'. The glasses HUD renderer reads this "
            "to choose pose blends. Empty dict = use STATE_PROFILES defaults."
        ),
    )
    created_at: float = Field(
        default=0.0,
        description="Epoch seconds when the character was created.",
    )
    updated_at: float = Field(
        default=0.0,
        description="Epoch seconds of last edit.",
    )

    model_config = {"extra": "forbid"}
