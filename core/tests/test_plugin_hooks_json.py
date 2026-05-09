"""Phase 18.1 — assert claude-code-plugin/hooks/hooks.json matches _HOOK_ENTRY × 5."""
import json
from pathlib import Path

from claude_code_talker.api import _HOOK_ENTRY, _HOOK_EVENT_NAMES

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent / "claude-code-plugin"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"


def test_hooks_json_exists():
    assert HOOKS_JSON.is_file(), f"missing: {HOOKS_JSON}"


def test_hooks_json_has_all_5_events():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for event in _HOOK_EVENT_NAMES:
        assert event in data, f"missing event: {event}"


def test_hooks_json_command_matches_hook_entry():
    """Each event's hook command should match the literal _HOOK_ENTRY shape."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for event in _HOOK_EVENT_NAMES:
        entries = data[event]
        assert len(entries) == 1
        entry = entries[0]
        assert entry == {
            "hooks": [
                {
                    "type": "command",
                    "shell": "powershell",
                    "command": "claude-code-talker-hook",
                    "async": True,
                }
            ]
        }


def test_hooks_json_consistent_with_hook_entry_constant():
    """Drift check: if api.py:_HOOK_ENTRY changes, this test points at hooks.json."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    expected = _HOOK_ENTRY  # {"hooks": [{...}]}
    for event in _HOOK_EVENT_NAMES:
        assert data[event][0] == expected, (
            f"hooks.json[{event}] drifted from api.py:_HOOK_ENTRY. "
            "Update both together."
        )
