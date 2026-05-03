"""Tests for SessionCatalog."""
import pytest
from pathlib import Path
from claude_code_talker.catalog import SessionCatalog, CatalogEntry


def test_catalog_entry_default_fields():
    e = CatalogEntry(session_id="abc", project_slug="MyProj",
                     transcript_path=Path("/t/abc.jsonl"), last_modified=1.0)
    assert e.session_id == "abc"
    assert e.project_slug == "MyProj"
    assert e.last_modified == 1.0


def test_catalog_starts_empty():
    c = SessionCatalog(projects_dir=Path("/does/not/exist"))
    assert c.entries() == []


def test_entry_for_returns_none_when_missing(tmp_path):
    c = SessionCatalog(projects_dir=tmp_path)
    assert c.entry_for("nope") is None


def test_scan_empty_dir(tmp_path):
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert c.entries() == []


def test_scan_missing_dir():
    c = SessionCatalog(projects_dir=Path("/does/not/exist"))
    c.scan()
    assert c.entries() == []


def test_scan_finds_transcripts(tmp_path):
    """Three projects with two transcripts each — should find 6 entries (unique session_ids)."""
    sid_counter = 0
    expected_ids: set[str] = set()
    for proj in ["C--proj-a", "C--proj-b", "C--proj-c"]:
        d = tmp_path / proj
        d.mkdir()
        for _ in range(2):
            sid = f"sess-{sid_counter:06d}"
            (d / f"{sid}.jsonl").write_text("")
            expected_ids.add(sid)
            sid_counter += 1
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert len(c.entries()) == 6
    ids = {e.session_id for e in c.entries()}
    assert ids == expected_ids


def test_scan_records_mtime(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    f = d / "abc.jsonl"
    f.write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    e = c.entry_for("abc")
    assert e is not None
    assert e.last_modified > 0


def test_scan_ignores_non_jsonl(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "abc.jsonl").write_text("")
    (d / "readme.txt").write_text("ignore me")
    (d / "notes.md").write_text("ignore me too")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert len(c.entries()) == 1
    assert c.entry_for("abc") is not None
