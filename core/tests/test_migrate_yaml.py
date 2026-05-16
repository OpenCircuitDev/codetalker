"""
Tests for the legacy YAML → SessionStore migration.

These tests verify three properties:

  1. **Faithful migration**: a realistic YAML in the legacy format
     produces an equivalent Session in the store.

  2. **Isolation**: one bad YAML doesn't abort the run — the rest
     of the migration completes and the failure is reported.

  3. **Dry-run safety**: dry_run=True writes nothing. The DB stays
     empty even when the YAMLs are valid.

The fixtures mirror the actual YAML shapes observed in the user's
~/.claude/scripts/codetalker/sessions/ directory.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from claude_code_talker.schemas import Session
from claude_code_talker.store import SessionStore
from claude_code_talker.store.migrate_yaml import (
    MigrationReport,
    migrate,
    yaml_to_session,
)


# ---------------------------------------------------------------------------
# Fixture: a realistic YAML directory with several files.
# ---------------------------------------------------------------------------


REALISTIC_YAML = """
live_overlay:
  active_mode: brief
  voice:
    model: en_US-joe-medium
    engine: piper
  paths:
    handling: omit
  code_blocks: stub
  live:
    cadence: significant_only
  markup:
    code_fence:
      kind: skip
    tool_output:
      kind: describe
    inline_code:
      kind: identifier_only
    todo_update:
      kind: count_only
attached_profile: null
enabled: true
display_name: OCR-Web
last_modified: 1778357833.8549354
workspace_group: OCRacing
auto_mode_enabled: false
audio_outputs:
- phone
cwd: C:\\Users\\brand\\Dropbox\\OCR\\Open_Circuit\\BF-Workspace
"""


@pytest.fixture
def yaml_dir(tmp_path: Path) -> Path:
    """A directory with three YAMLs: one realistic, one minimal, one corrupt."""
    d = tmp_path / "sessions_yaml"
    d.mkdir()

    # Realistic — full live_overlay tree.
    (d / "2eb5c985-63fc-4731-af93-1e824011f3c6.yaml").write_text(
        REALISTIC_YAML, encoding="utf-8"
    )

    # Minimal — only display_name + enabled.
    (d / "minimal-sid.yaml").write_text(
        "display_name: Minimal Test\nenabled: true\n", encoding="utf-8"
    )

    # Corrupt — not parseable YAML.
    (d / "corrupt-sid.yaml").write_text(
        "this: is: not: yaml: { broken\n", encoding="utf-8"
    )

    return d


@pytest.fixture
def store(tmp_path: Path):
    s = SessionStore(tmp_path / "sessions.db")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Single-file translation.
# ---------------------------------------------------------------------------


def test_yaml_to_session_realistic(yaml_dir: Path):
    yp = yaml_dir / "2eb5c985-63fc-4731-af93-1e824011f3c6.yaml"
    session, dropped = yaml_to_session(yp)

    # Identity
    assert session.session_id == "2eb5c985-63fc-4731-af93-1e824011f3c6"
    assert session.display_name == "OCR-Web"
    assert session.workspace_group == "OCRacing"

    # Speaking
    assert session.active_mode == "brief"
    assert session.enabled is True
    assert session.auto_mode_enabled is False
    assert session.cadence == "significant_only"

    # Audio routing
    assert session.audio_outputs == ["phone"]

    # Voice
    assert session.voice.engine == "piper"
    assert session.voice.model == "en_US-joe-medium"

    # Narration (flattened out of live_overlay)
    assert session.narration.paths_handling == "omit"
    assert session.narration.code_blocks == "stub"
    assert "code_fence" in session.narration.markup
    assert session.narration.markup["code_fence"].kind == "skip"
    assert session.narration.markup["tool_output"].kind == "describe"

    # Timestamps preserved
    assert session.last_modified > 0
    assert session.cwd is not None
    assert "BF-Workspace" in session.cwd

    # No keys were silently dropped on a valid file.
    assert dropped == [], f"unexpected dropped keys: {dropped}"


def test_yaml_to_session_minimal(yaml_dir: Path):
    """A YAML with only display_name + enabled. Everything else
    falls back to schema defaults."""
    yp = yaml_dir / "minimal-sid.yaml"
    session, dropped = yaml_to_session(yp)

    assert session.session_id == "minimal-sid"
    assert session.display_name == "Minimal Test"
    assert session.enabled is True
    # Defaults applied:
    assert session.active_mode == "brief"
    assert session.audio_outputs == ["desktop"]
    assert session.workspace_group is None
    assert session.narration.paths_handling == "filename"  # default


def test_yaml_to_session_corrupt_raises(yaml_dir: Path):
    """Bad YAML raises so the runner can catch + report it."""
    yp = yaml_dir / "corrupt-sid.yaml"
    with pytest.raises(Exception):
        yaml_to_session(yp)


# ---------------------------------------------------------------------------
# Run-level: full migration over a directory.
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write(store: SessionStore, yaml_dir: Path):
    """Dry-run reports outcomes but never touches the DB."""
    report = migrate(store, yaml_dir, dry_run=True)

    assert report.dry_run is True
    assert report.backup_path is None  # backups only happen on apply
    assert report.total_yaml_files == 3
    # 2 successful translations (realistic + minimal), 1 failure (corrupt).
    assert len(report.migrated) == 2
    assert len(report.failures) == 1
    assert "corrupt" in report.failures[0].yaml_path.name

    # DB is still empty.
    assert store.count() == 0


def test_apply_migrates_into_store(store: SessionStore, yaml_dir: Path, tmp_path: Path):
    """apply=True writes to the store and produces a YAML backup."""
    backup_dir = tmp_path / "yaml_backup"
    report = migrate(store, yaml_dir, dry_run=False, backup_dir=backup_dir)

    assert report.dry_run is False
    assert report.backup_path == backup_dir
    assert backup_dir.exists()
    # Backup contains every original YAML.
    assert {p.name for p in backup_dir.glob("*.yaml")} == {
        "2eb5c985-63fc-4731-af93-1e824011f3c6.yaml",
        "minimal-sid.yaml",
        "corrupt-sid.yaml",
    }

    # Successful migrations are in the store.
    assert store.count() == 2
    s = store.get("2eb5c985-63fc-4731-af93-1e824011f3c6")
    assert s is not None
    assert s.display_name == "OCR-Web"
    assert s.workspace_group == "OCRacing"

    minimal = store.get("minimal-sid")
    assert minimal is not None
    assert minimal.display_name == "Minimal Test"


def test_corrupt_file_doesnt_abort_run(store: SessionStore, yaml_dir: Path):
    """The realistic + minimal still migrate even when corrupt YAML is present."""
    report = migrate(store, yaml_dir, dry_run=False, backup_dir=yaml_dir.parent / "bkp")
    assert len(report.migrated) == 2
    assert len(report.failures) == 1


def test_missing_yaml_dir_yields_empty_report(store: SessionStore, tmp_path: Path):
    """Pointing at a non-existent dir is not an error; just yields zero migrations."""
    bogus = tmp_path / "does_not_exist"
    report = migrate(store, bogus, dry_run=True)
    assert report.total_yaml_files == 0
    assert report.migrated == []
    assert report.failures == []


def test_audio_outputs_filters_invalid_values(tmp_path: Path):
    """Unknown audio_output strings are dropped, not stored."""
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    (yaml_dir / "test.yaml").write_text(
        yaml.safe_dump({
            "display_name": "Test",
            "enabled": True,
            "audio_outputs": ["desktop", "headphones", "phone"],
        }),
        encoding="utf-8",
    )

    session, _ = yaml_to_session(yaml_dir / "test.yaml")
    # 'headphones' is not a valid AudioOutput; it gets filtered.
    assert set(session.audio_outputs) == {"desktop", "phone"}


def test_unknown_top_level_key_dropped_with_report(tmp_path: Path):
    """Unknown YAML top-level keys are dropped and reported."""
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    (yaml_dir / "test.yaml").write_text(
        yaml.safe_dump({
            "display_name": "Test",
            "experimental_feature": True,  # unknown
        }),
        encoding="utf-8",
    )

    session, dropped = yaml_to_session(yaml_dir / "test.yaml")
    assert session.display_name == "Test"
    assert "top:experimental_feature" in dropped


def test_markup_kind_validation_drops_invalid(tmp_path: Path):
    """A markup form with an invalid kind for that form is dropped."""
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    (yaml_dir / "test.yaml").write_text(
        yaml.safe_dump({
            "display_name": "Test",
            "live_overlay": {
                "markup": {
                    "code_fence": {"kind": "fly_away"},  # not in FORM_KINDS
                },
            },
        }),
        encoding="utf-8",
    )

    session, dropped = yaml_to_session(yaml_dir / "test.yaml")
    # markup with invalid kind didn't make it in.
    assert "code_fence" not in session.narration.markup
    assert any("narration_validation_error" in d or "markup.code_fence" in d for d in dropped)
