"""Phase 26 — Tag.markup_overrides field + per-tag markup overlay during live dispatch."""
from __future__ import annotations

from claude_code_talker.markup.pipeline import transform_for_live
from claude_code_talker.triggers.tags import Tag, TagLibrary


def test_tag_dataclass_has_markup_overrides_field_with_default_empty():
    tag = Tag(id="audible_summary", display_name="Audible Summary")
    assert tag.markup_overrides == {}


def test_tag_with_markup_overrides_applies_during_live_dispatch():
    tag = Tag(
        id="audible_plan_entry",
        display_name="Audible Plan Entry",
        markup_overrides={"plan_block": {"kind": "read"}},
    )
    cfg = {"mode": "brief", "markup": {"plan_block": {"kind": "skip"}}}
    body = "## Plan\nstep one\nstep two"
    out = transform_for_live(body, cfg, tag.markup_overrides)
    assert "step one" in out


def test_taglibrary_from_cfg_accepts_markup_overrides():
    cfg_section = {
        "audible_plan_entry": {
            "display_name": "Audible Plan Entry",
            "enabled": True,
            "editor_mode": "structured",
            "when_to_trigger": "",
            "format_template": "",
            "example": "",
            "freeform_text": "",
            "markup_overrides": {"plan_block": {"kind": "read"}},
        }
    }
    lib = TagLibrary.from_cfg(cfg_section)
    tag = lib.get("audible_plan_entry")
    assert tag is not None
    assert tag.markup_overrides == {"plan_block": {"kind": "read"}}


def test_taglibrary_from_cfg_silently_drops_missing_markup_overrides():
    """Backward compat: existing tags without markup_overrides default to empty."""
    cfg_section = {
        "audible_summary": {
            "display_name": "Audible Summary",
            "enabled": True,
            "editor_mode": "structured",
            "when_to_trigger": "",
            "format_template": "",
            "example": "",
            "freeform_text": "",
        }
    }
    lib = TagLibrary.from_cfg(cfg_section)
    tag = lib.get("audible_summary")
    assert tag is not None
    assert tag.markup_overrides == {}
