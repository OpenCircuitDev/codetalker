"""Configuration loading with three-layer deep merge.

Layers (later wins):
  1. Preset defaults (from presets.py)
  2. Global config: ~/.claude/scripts/tts_config.yaml
  3. Workspace config: <cwd>/.claude/tts_workspace.yaml (handled in workspace.py)
"""
from __future__ import annotations

from pathlib import Path

import yaml

from claude_code_talker.presets import get_preset

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

    Returns a safe-default dict if the file is missing, unreadable, malformed,
    or contains non-dict top-level YAML.
    """
    p = path if path is not None else DEFAULT_GLOBAL_PATH
    if not p.exists():
        return {"enabled": True}
    try:
        with open(p, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        if not isinstance(user_cfg, dict):
            return {"enabled": True}
    except (OSError, yaml.YAMLError):
        return {"enabled": True}
    preset_name = user_cfg.get("preset")
    preset = get_preset(preset_name) if preset_name else {}
    return deep_merge(preset, user_cfg)


def find_workspace_config(cwd: str | None) -> Path | None:
    """Walk up from cwd looking for .claude/tts_workspace.yaml."""
    if not cwd:
        return None
    try:
        p = Path(cwd).resolve()
    except (OSError, ValueError):
        return None
    for d in [p, *p.parents]:
        candidate = d / ".claude" / "tts_workspace.yaml"
        if candidate.exists():
            return candidate
    return None


def translate_workspace_overrides(ws_cfg: dict) -> dict:
    """Convert friendly hear/dont-hear field schema to internal config overrides."""
    o: dict = {}
    if not ws_cfg:
        return o

    if "voice" in ws_cfg:
        o.setdefault("voice", {})["model"] = ws_cfg["voice"]
    if "rate" in ws_cfg:
        o.setdefault("voice", {})["rate"] = ws_cfg["rate"]

    prose = ws_cfg.get("prose")
    if prose == "none":
        o.setdefault("content_filter", {})["mode"] = "suppress"
    elif prose == "conclusions":
        o.setdefault("content_filter", {})["mode"] = "whitelist"
    elif prose == "full":
        o.setdefault("content_filter", {})["mode"] = "blacklist"

    syn = ws_cfg.get("synopsis")
    if syn == "none":
        o.setdefault("synopsis", {})["enabled"] = False
    elif syn in ("brief", "full"):
        o.setdefault("synopsis", {})["enabled"] = True
        o.setdefault("synopsis", {})["style"] = syn

    todos = ws_cfg.get("todos") or {}
    if todos:
        completed = todos.get("completed", "skip")
        o.setdefault("todos", {})["enabled"] = True
        o.setdefault("todos", {})["speak_completed"] = completed == "speak"

    elements: dict = {}
    if (cb := ws_cfg.get("code_blocks")) in ("speak", "stub"):
        elements["code_block"] = cb == "speak"
    if (tb := ws_cfg.get("tables")) in ("speak", "stub"):
        elements["table"] = tb == "speak"
    if (ib := ws_cfg.get("insight_blocks")) in ("speak", "skip"):
        elements["insight_block"] = ib == "speak"
    if elements:
        o["elements"] = elements

    fp = ws_cfg.get("file_paths")
    if fp in ("filename", "omit", "the_file"):
        o.setdefault("paths", {})["handling"] = fp

    if ws_cfg.get("tool_descriptors") == "speak":
        o.setdefault("content_filter", {})["skip_paragraph_patterns"] = []

    return o


CFG_OVERLAY_PATH = Path.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"


def _load_cfg_overlay() -> dict:
    """Load the user-edited cfg overlay (UI-managed settings like default LLM
    provider/model). Always wins over the base cfg. Returns {} if missing or
    malformed.
    """
    if not CFG_OVERLAY_PATH.exists():
        return {}
    try:
        with open(CFG_OVERLAY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, yaml.YAMLError):
        return {}


def load_full_config(global_path: Path | None = None, cwd: str | None = None) -> dict:
    """Load global + workspace + UI-overlay configs and produce a fully
    resolved config dict. Layer order (later wins):
      1. Preset defaults
      2. Global config (~/.claude/scripts/tts_config.yaml)
      3. Workspace config (<cwd>/.claude/tts_workspace.yaml)
      4. UI overlay (~/.claude/scripts/codetalker/cfg-overlay.yaml) — written
         by codetalker's UI when the user clicks "Save as default" etc.
    """
    cfg = load_global_config(global_path)
    ws_path = find_workspace_config(cwd)
    if ws_path:
        try:
            with open(ws_path, encoding="utf-8") as f:
                ws_cfg = yaml.safe_load(f) or {}
            if not isinstance(ws_cfg, dict):
                ws_cfg = {}
            cfg = deep_merge(cfg, translate_workspace_overrides(ws_cfg))
        except (OSError, yaml.YAMLError):
            pass
    overlay = _load_cfg_overlay()
    if overlay:
        cfg = deep_merge(cfg, overlay)
    return cfg


# ---------------------------------------------------------------------------
# Session-scoped resolver (imports at bottom to avoid circular imports)
# ---------------------------------------------------------------------------

import copy  # noqa: E402
import logging  # noqa: E402

from claude_code_talker.sessions import SessionState  # noqa: E402
from claude_code_talker.profiles import ProfileStore  # noqa: E402


def resolve_for_session(
    base_cfg: dict,
    session: SessionState,
    profile_store: ProfileStore,
    character_store=None,
) -> dict:
    """Merge base_cfg → profile (if attached) → character (if attached) → session.live_overlay.

    base_cfg is the existing preset → global → workspace merge.
    Character supplies only voice.model and triggers.persona; never behavior fields.
    Caches the resolved dict on session.cached_cfg; returns the cache on
    subsequent calls. Caller must invalidate via SessionRegistry.invalidate
    when overlay or attached_profile changes.
    """
    if session.cached_cfg is not None:
        return session.cached_cfg

    resolved = copy.deepcopy(base_cfg)

    if session.attached_profile:
        try:
            profile_content = profile_store.get(session.attached_profile)
            _deep_merge_inplace(resolved, profile_content)
        except FileNotFoundError:
            logging.warning(
                "session %s references missing profile %s; falling through",
                session.session_id, session.attached_profile,
            )

    # Phase 25a — character identity merge (between profile and overlay).
    # Character supplies only voice.model and triggers.persona; never behavior fields.
    char_id = getattr(session, "attached_character", None)
    if char_id and character_store is not None:
        char = character_store.get(char_id)
        if char is not None:
            _deep_merge_inplace(resolved, {
                "voice": {"model": char.voice_ref},
                "triggers": {"persona": char.persona},
            })

    if session.live_overlay:
        _deep_merge_inplace(resolved, session.live_overlay)

    session.cached_cfg = resolved
    return resolved


def _deep_merge_inplace(base: dict, overlay: dict) -> None:
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge_inplace(base[k], v)
        else:
            base[k] = v
