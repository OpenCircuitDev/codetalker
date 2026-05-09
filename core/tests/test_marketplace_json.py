"""Phase 19.1 — assert .claude-plugin/marketplace.json catalog is well-formed."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def test_marketplace_json_exists():
    assert MARKETPLACE_JSON.is_file(), f"missing: {MARKETPLACE_JSON}"


def test_marketplace_json_required_fields():
    data = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    assert data["name"] == "codetalker"
    assert isinstance(data["owner"], dict)
    assert data["owner"].get("name")
    assert isinstance(data["plugins"], list) and data["plugins"]


def test_marketplace_json_codetalker_plugin_entry():
    data = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    plugin = next((p for p in data["plugins"] if p["name"] == "codetalker"), None)
    assert plugin is not None, "codetalker plugin missing from marketplace"
    assert plugin["source"] == "./claude-code-plugin"
    assert plugin.get("license") == "MIT"
    assert "homepage" in plugin
    assert "repository" in plugin


def test_marketplace_json_no_pinned_version():
    """Per Phase 19 decision: omit version, let git SHA drive updates."""
    data = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    for p in data["plugins"]:
        assert "version" not in p, (
            f"plugin {p['name']!r} has a pinned version; per Phase 19 we omit "
            "version so git commit SHA drives updates."
        )


def test_marketplace_name_not_reserved():
    """Anthropic reserves certain marketplace names; ensure we don't use them."""
    reserved = {
        "claude-code-marketplace", "claude-code-plugins",
        "claude-plugins-official", "anthropic-marketplace",
        "anthropic-plugins", "agent-skills", "knowledge-work-plugins",
        "life-sciences",
    }
    data = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))
    assert data["name"] not in reserved
