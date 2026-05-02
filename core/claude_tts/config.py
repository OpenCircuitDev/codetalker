"""Configuration loading with three-layer deep merge.

Layers (later wins):
  1. Preset defaults (from presets.py)
  2. Global config: ~/.claude/scripts/tts_config.yaml
  3. Workspace config: <cwd>/.claude/tts_workspace.yaml (handled in workspace.py)
"""
from __future__ import annotations

from pathlib import Path

import yaml

from claude_tts.presets import get_preset

DEFAULT_GLOBAL_PATH = Path.home() / ".claude" / "scripts" / "tts_config.yaml"


def deep_merge(base: dict, override: dict | None) -> dict:
    """Deep-merge override on top of base. Override wins on leaves; lists replace."""
    out = dict(base)
    if not override:
        return out
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_global_config(path: Path | None = None) -> dict:
    """Load the global config file, applying its declared preset as defaults.

    Returns an empty-ish but valid dict if the file is missing.
    """
    p = path if path is not None else DEFAULT_GLOBAL_PATH
    if not p.exists():
        return {"enabled": True}

    with open(p, encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}

    preset_name = user_cfg.get("preset")
    preset = get_preset(preset_name) if preset_name else {}
    return deep_merge(preset, user_cfg)
