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
