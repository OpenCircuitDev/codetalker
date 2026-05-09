"""Phase 26 — markup.forms tests."""
from __future__ import annotations

import pytest

from claude_code_talker.markup.forms import (
    FORM_KINDS,
    PRESETS,
    Treatment,
    load_treatments,
    preset_for_mode,
    validate_treatment,
)


def test_form_kinds_contains_ten_forms():
    expected = {
        "code_fence", "inline_code", "todo_update", "plan_block",
        "audible_block", "system_reminder", "tool_output",
        "subagent_dispatch", "file_path", "long_numeral",
    }
    assert set(FORM_KINDS) == expected


def test_treatment_validates_known_kind():
    t = Treatment(kind="skip")
    validate_treatment("code_fence", t)  # no raise


def test_treatment_rejects_unknown_kind_for_form():
    t = Treatment(kind="bogus")
    with pytest.raises(ValueError, match="bogus"):
        validate_treatment("code_fence", t)


def test_audible_block_locked_to_speak():
    assert FORM_KINDS["audible_block"] == {"speak"}


def test_preset_for_mode_brief_returns_full_table():
    presets = preset_for_mode("brief")
    assert presets["code_fence"].kind == "skip"
    assert presets["inline_code"].kind == "identifier_only"
    assert presets["audible_block"].kind == "speak"


def test_preset_for_mode_unknown_falls_back_to_direct():
    presets = preset_for_mode("nonsense")
    direct = preset_for_mode("direct")
    assert presets == direct


def test_load_treatments_overlays_user_values_on_preset():
    cfg = {"mode": "brief", "markup": {"code_fence": {"kind": "describe"}}}
    out = load_treatments(cfg)
    assert out["code_fence"].kind == "describe"  # user override
    assert out["inline_code"].kind == "identifier_only"  # preset floor


def test_load_treatments_invalid_user_kind_falls_back_to_preset():
    cfg = {"mode": "direct", "markup": {"code_fence": {"kind": "bogus"}}}
    out = load_treatments(cfg)
    assert out["code_fence"].kind == "describe"  # direct preset for code_fence


# ---------------------------------------------------------------------------
# Phase 26 Task 13 — legacy cfg key compat shim
# ---------------------------------------------------------------------------

def test_load_treatments_honors_legacy_paths_handling():
    cfg = {"mode": "direct", "text": {"paths": {"handling": "describe"}}}
    out = load_treatments(cfg)
    assert out["file_path"].kind == "describe"


def test_load_treatments_legacy_paths_handling_overridden_by_markup():
    """When both legacy and new keys exist, the explicit markup.* wins."""
    cfg = {
        "mode": "direct",
        "text": {"paths": {"handling": "describe"}},
        "markup": {"file_path": {"kind": "read"}},
    }
    out = load_treatments(cfg)
    assert out["file_path"].kind == "read"


def test_load_treatments_honors_legacy_elements_code_block():
    cfg = {"mode": "direct", "elements": {"code_block": "skip"}}
    out = load_treatments(cfg)
    assert out["code_fence"].kind == "skip"


def test_load_treatments_legacy_elements_code_block_overridden_by_markup():
    cfg = {
        "mode": "direct",
        "elements": {"code_block": "skip"},
        "markup": {"code_fence": {"kind": "read"}},
    }
    out = load_treatments(cfg)
    assert out["code_fence"].kind == "read"


def test_load_treatments_invalid_legacy_value_ignored():
    cfg = {"mode": "direct", "text": {"paths": {"handling": "bogus"}}}
    out = load_treatments(cfg)
    # Falls back to the direct preset's file_path → filename
    assert out["file_path"].kind == "filename"
