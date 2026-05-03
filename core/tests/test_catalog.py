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


def test_slug_for_simple_folder(tmp_path):
    """A folder ending in '-MyProj' should produce slug 'MyProj'."""
    d = tmp_path / "C--Users-brand-Dropbox-MyProj"
    d.mkdir()
    (d / "abc.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert c.entry_for("abc").project_slug == "MyProj"


def test_slug_for_deep_path(tmp_path):
    """Slug is just the trailing segment, regardless of how deep."""
    d = tmp_path / "C--Users-brand-Dropbox-OCR-Open-Circuit-BF-Workspace"
    d.mkdir()
    (d / "abc.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert c.entry_for("abc").project_slug == "Workspace"


def test_slug_for_folder_without_hyphens(tmp_path):
    """Folder name with no hyphens — return the whole name."""
    d = tmp_path / "JustOneWord"
    d.mkdir()
    (d / "abc.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert c.entry_for("abc").project_slug == "JustOneWord"


def test_entries_for_project_filters(tmp_path):
    proj_a = tmp_path / "C--proj-a"
    proj_b = tmp_path / "C--proj-b"
    proj_a.mkdir()
    proj_b.mkdir()
    (proj_a / "aaa.jsonl").write_text("")
    (proj_a / "bbb.jsonl").write_text("")
    (proj_b / "ccc.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    in_a = c.entries_for_project("a")
    in_b = c.entries_for_project("b")
    assert {e.session_id for e in in_a} == {"aaa", "bbb"}
    assert {e.session_id for e in in_b} == {"ccc"}


def test_entries_for_project_unknown_returns_empty(tmp_path):
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert c.entries_for_project("never-existed") == []


import os
import time


def test_scan_caps_at_max_entries(tmp_path):
    """When more transcripts exist than max_entries, keep only most-recent-mtime."""
    d = tmp_path / "C--proj"
    d.mkdir()
    # Create 10 transcripts with increasing mtimes
    for i in range(10):
        f = d / f"sess{i:02d}.jsonl"
        f.write_text("")
        os.utime(f, (i, i))  # mtime = i
    c = SessionCatalog(projects_dir=tmp_path, max_entries=5)
    c.scan()
    # Only the 5 most-recent (sess05..sess09) should survive
    ids = {e.session_id for e in c.entries()}
    assert ids == {"sess05", "sess06", "sess07", "sess08", "sess09"}


def test_scan_does_not_cap_when_under_limit(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    for i in range(3):
        (d / f"s{i}.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path, max_entries=500)
    c.scan()
    assert len(c.entries()) == 3


def test_refresh_picks_up_new_files(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "first.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    assert len(c.entries()) == 1
    # Add another transcript
    (d / "second.jsonl").write_text("")
    c.refresh()
    assert len(c.entries()) == 2


def test_watcher_starts_and_stops(tmp_path):
    c = SessionCatalog(projects_dir=tmp_path)
    c.start_watcher(interval_seconds=0.05)
    assert c._watcher_thread is not None
    assert c._watcher_thread.is_alive()
    c.stop_watcher()
    time.sleep(0.1)
    assert not c._watcher_thread.is_alive()


def test_watcher_picks_up_new_files(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "first.jsonl").write_text("")
    c = SessionCatalog(projects_dir=tmp_path)
    c.scan()
    c.start_watcher(interval_seconds=0.05)
    (d / "second.jsonl").write_text("")
    time.sleep(0.2)  # allow watcher to refresh
    c.stop_watcher()
    assert len(c.entries()) == 2
