"""Voice metadata sidecar JSON read/write at references/<name>.json.

Each cloned voice has a companion JSON file that records where it came from,
what clip range was used, and (later) which GLB avatar is attached.  The sidecar
is written atomically (tmp → rename) so a crash mid-write never corrupts it.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path


@dataclass
class VoiceMetadata:
    name: str
    source_path: str = ""           # original local file path
    source_type: str = "audio"      # "audio" | "video"
    clip_start: float = 0.0
    clip_end: float = 0.0
    face_source: str = ""           # "rpm_photo" | "starter" | "rpm_creator" | "upload_glb" | "upload_fbx" | ""
    rpm_avatar_id: str = ""
    starter_id: str = ""
    created_at: float = 0.0


def metadata_path(references_dir: Path, name: str) -> Path:
    """Return the expected sidecar path for a voice name."""
    return references_dir / f"{name}.json"


def read_metadata(references_dir: Path, name: str) -> VoiceMetadata | None:
    """Return a VoiceMetadata for *name*, or None if the sidecar is missing or corrupted."""
    p = metadata_path(references_dir, name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    # Filter to known fields only — drop any future or unknown keys gracefully.
    known = {f.name for f in fields(VoiceMetadata)}
    safe = {k: v for k, v in data.items() if k in known}
    # Always trust the filename as the canonical name.
    safe["name"] = name
    try:
        return VoiceMetadata(**safe)
    except TypeError:
        return None


def write_metadata(references_dir: Path, meta: VoiceMetadata) -> Path:
    """Write *meta* to a sidecar JSON file.  Atomic: writes .tmp then renames."""
    references_dir.mkdir(parents=True, exist_ok=True)
    p = metadata_path(references_dir, meta.name)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return p


def update_metadata(references_dir: Path, name: str, **changes) -> VoiceMetadata:
    """Read-modify-write helper.

    Reads an existing sidecar (or creates a fresh VoiceMetadata if none exists),
    applies *changes*, writes it back, and returns the updated object.
    """
    meta = read_metadata(references_dir, name) or VoiceMetadata(name=name)
    for k, v in changes.items():
        if hasattr(meta, k):
            setattr(meta, k, v)
    write_metadata(references_dir, meta)
    return meta


def new_metadata(name: str, *, source_path: str = "", source_type: str = "audio",
                 clip_start: float = 0.0, clip_end: float = 0.0) -> VoiceMetadata:
    """Convenience constructor that fills in created_at automatically."""
    return VoiceMetadata(
        name=name,
        source_path=source_path,
        source_type=source_type,
        clip_start=clip_start,
        clip_end=clip_end,
        created_at=time.time(),
    )
