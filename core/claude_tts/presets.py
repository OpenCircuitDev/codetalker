"""Preset bundle definitions.

A preset is a dict of internal config defaults that gets deep-merged underneath
the user's global config, so explicit user settings always win.
"""
from __future__ import annotations

PRESETS: dict[str, dict] = {
    "monitor": {
        "text": {"max_chars": 3000, "boundary_snap": "paragraph"},
        "content_filter": {"mode": "blacklist"},
        "synopsis": {"enabled": True, "style": "brief", "position": "append"},
        "paths": {"handling": "filename"},
    },
    "synopsis": {
        "text": {"max_chars": 800, "boundary_snap": "sentence"},
        "content_filter": {"mode": "suppress"},
        "synopsis": {"enabled": True, "style": "full", "position": "prepend"},
        "paths": {"handling": "filename"},
        "todos": {"enabled": True, "speak_completed": True},
    },
    "conclusions": {
        "text": {"max_chars": 800, "boundary_snap": "sentence"},
        "content_filter": {"mode": "whitelist"},
        "synopsis": {"enabled": True, "style": "brief", "position": "prepend"},
        "paths": {"handling": "omit"},
    },
    "brief": {
        "text": {"max_chars": 1000, "boundary_snap": "sentence"},
        "content_filter": {"mode": "blacklist"},
        "synopsis": {"enabled": True, "style": "brief", "position": "prepend"},
        "paths": {"handling": "filename"},
    },
    "verbose": {
        "text": {"max_chars": 3000, "boundary_snap": "paragraph"},
        "content_filter": {"mode": "off"},
        "synopsis": {"enabled": True, "style": "full", "position": "append"},
        "paths": {"handling": "filename"},
        "elements": {"insight_block": True},
        "todos": {"enabled": True, "speak_completed": True},
    },
}


def get_preset(name: str) -> dict:
    """Return the preset dict for `name`, or {} if unknown."""
    return PRESETS.get(name, {})
