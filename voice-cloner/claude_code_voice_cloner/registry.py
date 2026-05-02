"""Reference WAV registry — save, list, remove."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_REGISTRY = Path.home() / ".claude" / "scripts" / "voice-cloner" / "references"


def registry_dir() -> Path:
    return DEFAULT_REGISTRY


def save_reference(name: str, wav_bytes: bytes, **metadata) -> Path:
    """Save a reference WAV plus sidecar metadata JSON."""
    DEFAULT_REGISTRY.mkdir(parents=True, exist_ok=True)
    wav_path = DEFAULT_REGISTRY / f"{name}.wav"
    json_path = DEFAULT_REGISTRY / f"{name}.json"
    wav_path.write_bytes(wav_bytes)
    json_path.write_text(json.dumps(metadata, indent=2))
    return wav_path


def list_references() -> list[str]:
    if not DEFAULT_REGISTRY.exists():
        return []
    return sorted(p.stem for p in DEFAULT_REGISTRY.glob("*.wav"))


def remove_reference(name: str) -> None:
    for ext in (".wav", ".json"):
        p = DEFAULT_REGISTRY / f"{name}{ext}"
        try:
            p.unlink()
        except FileNotFoundError:
            pass
