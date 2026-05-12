"""Tests for the workspace_group bulk-assign rules.

Locks in the rule precedence + matching semantics for
`scripts/bulk_assign_workspace_group.py`. The rules drive a one-shot
migration that organizes 86+ Claude Code sessions into the user's
mental categories (OCR / CodeTalker / OCDev) without per-session
clicking. If a rule changes shape, this test will fail loudly so we
notice the migration semantics drifted before someone runs --apply.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the script as a module — it isn't packaged, lives under scripts/.
SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "bulk_assign_workspace_group.py"
)


@pytest.fixture(scope="module")
def bulk_script():
    spec = importlib.util.spec_from_file_location("bulk_assign_ws", SCRIPT_PATH)
    assert spec and spec.loader, f"could not load {SCRIPT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bulk_assign_ws"] = mod
    spec.loader.exec_module(mod)
    return mod


def _session(**fields) -> dict:
    """Build a minimal session dict with optional overrides."""
    base = {
        "session_id": "sess-test-0000",
        "display_name": "",
        "cwd": "",
        "project_slug": "",
        "project_dir": "",
        "workspace_group": None,
    }
    base.update(fields)
    return base


def _assign(bulk_script, session: dict) -> str | None:
    """Run RULES on a session and return the matched target (or None)."""
    for pred, label in bulk_script.RULES:
        try:
            if pred(session):
                return label
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# CodeTalker rule
# ---------------------------------------------------------------------------

def test_codetalker_matches_display_name(bulk_script):
    assert _assign(bulk_script, _session(display_name="CodeTalker")) == "CodeTalker"
    assert _assign(bulk_script, _session(display_name="codetalker xyz")) == "CodeTalker"


def test_codetalker_matches_ct_prefix(bulk_script):
    assert _assign(bulk_script, _session(display_name="CTWeb")) == "CodeTalker"
    assert _assign(bulk_script, _session(display_name="ct-experiment")) == "CodeTalker"


def test_codetalker_matches_cwd(bulk_script):
    s = _session(cwd=r"C:\Users\brand\Dropbox\OCR\Open_Circuit\codetalker")
    assert _assign(bulk_script, s) == "CodeTalker"


def test_codetalker_matches_project_slug(bulk_script):
    assert _assign(bulk_script, _session(project_slug="codetalker")) == "CodeTalker"


# ---------------------------------------------------------------------------
# OCDev rule (must beat OCR for memory-palace / forge cwds)
# ---------------------------------------------------------------------------

def test_ocdev_wins_over_ocr_for_memory_palace(bulk_script):
    """The cwd `ocr-memory-palace` contains 'ocr', but the OCDev rule
    fires first because it precedes the broader OCR rule."""
    s = _session(
        display_name="Picking Up On A Buzzing Flamingo",
        cwd=r"C:\Users\brand\Dropbox\OCR\Open_Circuit\ocr-memory-palace",
    )
    assert _assign(bulk_script, s) == "OCDev"


def test_ocdev_matches_ocr_forge_cwd(bulk_script):
    s = _session(
        display_name="OCR-Forge work",
        cwd=r"C:\Users\brand\Dropbox\OCR\Open_Circuit\OCR-Forge",
    )
    assert _assign(bulk_script, s) == "OCDev"


def test_ocdev_matches_explicit_ocdev_in_name(bulk_script):
    assert _assign(bulk_script, _session(display_name="OCDev migration")) == "OCDev"


# ---------------------------------------------------------------------------
# OCR rule (broadest)
# ---------------------------------------------------------------------------

def test_ocr_matches_display_name(bulk_script):
    assert _assign(bulk_script, _session(display_name="OCRGame")) == "OCR"
    assert _assign(bulk_script, _session(display_name="ocrweb")) == "OCR"


def test_ocr_matches_bf_workspace_cwd(bulk_script):
    s = _session(cwd=r"C:\Users\brand\Dropbox\OCR\Open_Circuit\BF_Workspace")
    assert _assign(bulk_script, s) == "OCR"


def test_ocr_matches_open_circuit_root(bulk_script):
    s = _session(
        display_name="Some game stuff",
        cwd=r"C:\Users\brand\Dropbox\OCR\Open_Circuit\BlueprintForge",
    )
    assert _assign(bulk_script, s) == "OCR"


# ---------------------------------------------------------------------------
# No-rule sessions stay unassigned
# ---------------------------------------------------------------------------

def test_unrelated_session_stays_unassigned(bulk_script):
    s = _session(display_name="my-other-project", cwd="/Users/me/elsewhere")
    assert _assign(bulk_script, s) is None


def test_session_with_no_signal_stays_unassigned(bulk_script):
    assert _assign(bulk_script, _session()) is None


# ---------------------------------------------------------------------------
# plan_assignments + summarize_distribution
# ---------------------------------------------------------------------------

def test_plan_excludes_already_correct(bulk_script):
    sessions = [
        _session(session_id="a", display_name="OCRGame", workspace_group="OCR"),
        _session(session_id="b", display_name="OCRWeb", workspace_group=None),
        _session(session_id="c", display_name="random"),
    ]
    plan = bulk_script.plan_assignments(sessions)
    sids = {p[0] for p in plan}
    assert "a" not in sids, "already-correct session should not appear in plan"
    assert "b" in sids, "session needing migration should appear in plan"
    assert "c" not in sids, "no-rule session should not appear in plan"


def test_summary_counts_already_vs_will_change(bulk_script):
    sessions = [
        _session(session_id="a", display_name="OCRGame", workspace_group="OCR"),
        _session(session_id="b", display_name="OCRWeb", workspace_group=None),
        _session(session_id="c", display_name="CodeTalker", workspace_group=None),
        _session(session_id="d", display_name="random", cwd="/elsewhere"),
    ]
    summary = bulk_script.summarize_distribution(sessions)
    assert summary["OCR"] == {"already": 1, "will_change": 1}
    assert summary["CodeTalker"] == {"already": 0, "will_change": 1}
    assert summary["(no rule matched)"] == {"already": 1, "will_change": 0}
