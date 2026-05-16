"""
Audio decision layer.

Single source of truth for "should this session produce audio?" and
"where should this WAV go?" decisions. Replaces the scattered
cfg.get("enabled") checks across server.py / audio.py / hooks.py /
companion/api.py.

The goal: every audio gate is a function in this module. Every gate
returns a typed status (AudibleStatus) carrying its named reason.
The audio worker, the hook handlers, and the diagnostic UI all
consume the same decisions.

Phase 2 of docs/refactor-plan-2026-05-16.md.
"""
from __future__ import annotations

from .audibility import is_session_audible
from .audio_jobs import AudioJobRegistry
from .routing import route_audio_publish_key

__all__ = [
    "is_session_audible",
    "route_audio_publish_key",
    "AudioJobRegistry",
]
