"""Phase 18.4 — assert plugin SKILL.md frontmatter + daemon-aware injection."""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent / "claude-code-plugin"
SKILL_PATH = PLUGIN_ROOT / "skills" / "codetalker-narration" / "SKILL.md"


def test_skill_md_exists():
    assert SKILL_PATH.is_file(), f"missing: {SKILL_PATH}"


def test_skill_md_has_frontmatter():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must start with --- frontmatter"
    end_idx = text.find("\n---\n", 4)
    assert end_idx != -1, "SKILL.md frontmatter must end with --- on its own line"


def test_skill_md_frontmatter_fields():
    text = SKILL_PATH.read_text(encoding="utf-8")
    end_idx = text.find("\n---\n", 4)
    front = text[4:end_idx]
    assert "name: codetalker-narration" in front
    assert "description:" in front


def test_skill_md_injects_daemon_body():
    """The skill must pull live state from the daemon at activation time."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "/api/triggers/skill-body" in text, (
        "SKILL.md must inject `/api/triggers/skill-body` so it tracks live cfg"
    )
    assert "127.0.0.1:17832" in text, "SKILL.md must point at the daemon's loopback URL"


def test_skill_md_has_daemon_off_fallback():
    """If the daemon is off, the user should see a clean fallback message."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "daemon not running" in text.lower(), (
        "SKILL.md must include a fallback message for the daemon-off case"
    )
