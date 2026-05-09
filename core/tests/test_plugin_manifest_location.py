"""Phase 19.2 — plugin manifest must live at the spec-compliant path."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_ROOT = REPO_ROOT / "claude-code-plugin"
SPEC_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
LEGACY_PATH = PLUGIN_ROOT / "plugin.json"


def test_plugin_json_at_spec_path():
    assert SPEC_PATH.is_file(), f"missing: {SPEC_PATH}"


def test_plugin_json_parses_with_required_fields():
    data = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert data["name"] == "codetalker"
    assert data.get("description")


def test_plugin_json_legacy_path_removed():
    """Drift-prevention: the old <plugin>/plugin.json must not coexist with the spec path."""
    assert not LEGACY_PATH.exists(), (
        f"legacy plugin.json still exists at {LEGACY_PATH}; remove it so "
        "Claude Code loads only the spec-compliant manifest."
    )


def test_plugin_json_omits_pinned_version():
    """Per Phase 19 decision: omit version so git SHA drives updates."""
    data = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert "version" not in data, (
        "plugin.json has a pinned version; per Phase 19 we omit version "
        "so the git commit SHA drives updates."
    )
