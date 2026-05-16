"""
Voice configuration — the engine + model + speech rate triple.

Used both at the session level (per-session voice override) and at
the master config level (fleet default). Same model type, same wire
shape on both ends.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import VoiceEngine


class VoiceConfig(BaseModel):
    """
    A complete voice specification: which engine renders the TTS,
    which model within that engine, and at what rate.

    Validation:
      - `model` is unvalidated at the schema level because engines
        register voices dynamically (Piper voices are filesystem-
        scanned). The audio worker performs a cross-engine fallback
        if the named voice isn't found.
      - `rate` is clamped to [0.5, 2.0] — outside this range produces
        unintelligible audio in every engine we support.
    """

    engine: VoiceEngine = Field(
        default="piper",
        description="TTS provider. piper is the production default (offline, free).",
    )
    model: str = Field(
        default="",
        description=(
            "Voice model name within the engine. For piper, the filename "
            "stem of a .onnx model in ~/.claude/scripts/piper/voices/. "
            "Empty string means 'use engine default' — the audio worker "
            "picks engine.list_voices()[0]."
        ),
    )
    rate: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Speech rate multiplier. 1.0 = engine default, 1.2 = 20% faster.",
    )

    model_config = {
        # Don't silently accept extra fields on input — catches typos
        # at the API boundary instead of later when something silently
        # uses the engine default.
        "extra": "forbid",
    }
