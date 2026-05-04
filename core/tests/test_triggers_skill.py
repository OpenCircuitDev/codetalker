"""Tests for triggers.skill — SKILL.md atomic writer."""
import pytest
from pathlib import Path
from claude_code_talker.triggers.skill import (
    install_skill, skill_path, is_skill_installed, SKILL_DIR_NAME,
)


def test_skill_path_under_skill_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.triggers.skill._SKILLS_ROOT", tmp_path)
    p = skill_path()
    assert p.parent.name == SKILL_DIR_NAME
    assert p.name == "SKILL.md"


def test_install_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.triggers.skill._SKILLS_ROOT", tmp_path)
    install_skill("frontmatter\nbody content")
    p = skill_path()
    assert p.exists()
    assert "frontmatter" in p.read_text(encoding="utf-8")
    assert "body content" in p.read_text(encoding="utf-8")


def test_install_idempotent_overwrites(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.triggers.skill._SKILLS_ROOT", tmp_path)
    install_skill("v1 content")
    install_skill("v2 content")
    p = skill_path()
    text = p.read_text(encoding="utf-8")
    assert "v2 content" in text
    assert "v1 content" not in text


def test_is_installed_false_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.triggers.skill._SKILLS_ROOT", tmp_path)
    assert is_skill_installed() is False


def test_is_installed_true_after_install(monkeypatch, tmp_path):
    monkeypatch.setattr("claude_code_talker.triggers.skill._SKILLS_ROOT", tmp_path)
    install_skill("hello")
    assert is_skill_installed() is True
