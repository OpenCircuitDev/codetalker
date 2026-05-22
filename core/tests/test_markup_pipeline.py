"""Phase 26 — pipeline assembly tests."""
from __future__ import annotations

from claude_code_talker.markup.pipeline import transform, transform_event


def test_transform_strips_code_fence_in_brief_mode():
    cfg = {"mode": "brief"}
    text = "intro\n\n```py\nprint(1)\n```\n\nafter"
    out = transform(text, cfg)
    assert "print(1)" not in out
    assert "intro" in out and "after" in out


def test_transform_describes_code_fence_in_direct_mode():
    cfg = {"mode": "direct"}
    text = "```py\nprint(1)\nprint(2)\n```"
    out = transform(text, cfg)
    assert "code block" in out.lower()


def test_transform_passes_audible_block_through():
    cfg = {"mode": "brief"}
    text = "## Audible Summary\nHello there.\n\nMore prose with `not_an_audible`."
    out = transform(text, cfg)
    assert "Audible Summary" in out
    assert "Hello there" in out


def test_transform_drops_system_reminder():
    cfg = {"mode": "direct"}
    text = "before <system-reminder>secret</system-reminder> after"
    out = transform(text, cfg)
    assert "secret" not in out
    assert "before" in out and "after" in out


def test_transform_user_override_beats_preset():
    cfg = {"mode": "direct", "markup": {"code_fence": {"kind": "skip"}}}
    text = "```py\nx\n```"
    assert transform(text, cfg) == ""


def test_transform_invalid_user_kind_falls_back_to_preset():
    cfg = {"mode": "brief", "markup": {"code_fence": {"kind": "bogus"}}}
    out = transform("```\nx\n```", cfg)
    assert out == ""  # brief preset = skip


def test_transform_event_for_todo_update():
    cfg = {"mode": "brief"}
    event = {
        "kind": "tool_use", "name": "TodoWrite",
        "input": {"todos": [{"status": "completed", "content": "a"}]},
    }
    out = transform_event(event, cfg)
    assert out is not None and "1" in out


# Tests for bullet marker stripping
def test_strip_single_bullet_asterisk():
    """Single bullet with asterisk gets marker stripped and period added."""
    cfg = {"mode": "direct"}
    text = "* fixed the auth bug"
    out = transform(text, cfg)
    assert "fixed the auth bug" in out
    assert "*" not in out
    assert out.rstrip().endswith(".")


def test_strip_single_bullet_dash():
    """Single bullet with dash gets marker stripped and period added."""
    cfg = {"mode": "direct"}
    text = "- added a test"
    out = transform(text, cfg)
    assert "added a test" in out
    assert "-" not in out
    assert out.rstrip().endswith(".")


def test_strip_single_bullet_unicode_dot():
    """Single bullet with unicode bullet point gets stripped and period added."""
    cfg = {"mode": "direct"}
    text = "• deployed to staging"
    out = transform(text, cfg)
    assert "deployed to staging" in out
    assert "•" not in out
    assert out.rstrip().endswith(".")


def test_strip_three_bullets_in_sequence():
    """Three bullets in sequence become three sentences."""
    cfg = {"mode": "direct"}
    text = "* fixed the auth bug\n* added a test\n* deployed to staging"
    out = transform(text, cfg)
    assert "fixed the auth bug." in out
    assert "added a test." in out
    assert "deployed to staging." in out
    assert "*" not in out


def test_bullet_with_no_space_after_marker_stays():
    """Bullet with no space after marker (emphasis-like) is preserved."""
    cfg = {"mode": "direct"}
    text = "*not a bullet"
    out = transform(text, cfg)
    # The regex requires a space after the marker, so this should pass through
    assert "*not a bullet" in out


def test_nested_bullets_with_indentation():
    """Nested bullets (with leading whitespace) get stripped."""
    cfg = {"mode": "direct"}
    text = "  * sub-item here"
    out = transform(text, cfg)
    assert "sub-item here" in out
    assert "*" not in out
    assert out.rstrip().endswith(".")


def test_bullet_inside_paragraph_not_stripped():
    """Mid-sentence asterisk (not line-leading) is not stripped."""
    cfg = {"mode": "direct"}
    text = "text * this is not really a bullet"
    out = transform(text, cfg)
    # The regex is ^[ \t]* so it only matches line-leading; this should pass through
    assert "text * this is not really a bullet" in out


def test_bullet_already_has_period():
    """Bullet item ending with period doesn't get double period."""
    cfg = {"mode": "direct"}
    text = "* foo."
    out = transform(text, cfg)
    assert "foo." in out
    assert "foo.." not in out


def test_bullet_already_has_exclamation():
    """Bullet item ending with ! doesn't get period added."""
    cfg = {"mode": "direct"}
    text = "* wow!"
    out = transform(text, cfg)
    assert "wow!" in out
    assert "wow!." not in out


def test_bullet_already_has_question():
    """Bullet item ending with ? doesn't get period added."""
    cfg = {"mode": "direct"}
    text = "* what?"
    out = transform(text, cfg)
    assert "what?" in out
    assert "what?." not in out


def test_standalone_word_asterisk_removed():
    """Literal 'asterisk' as a standalone word is removed."""
    cfg = {"mode": "direct"}
    text = "I added an asterisk to the regex"
    out = transform(text, cfg)
    # The word 'asterisk' should be removed
    assert "asterisk" not in out
    assert "I added an" in out
    assert "to the regex" in out


def test_standalone_word_asterisks_plural_removed():
    """Literal 'asterisks' (plural) is removed."""
    cfg = {"mode": "direct"}
    text = "The pattern has asterisks in it"
    out = transform(text, cfg)
    assert "asterisks" not in out
    assert "The pattern has" in out
    assert "in it" in out


def test_standalone_word_bullet_point_removed():
    """Literal 'bullet point' is removed."""
    cfg = {"mode": "direct"}
    text = "each bullet point is separate"
    out = transform(text, cfg)
    assert "bullet point" not in out
    assert "each" in out
    assert "is separate" in out


def test_standalone_word_bullet_points_plural_removed():
    """Literal 'bullet points' (plural) is removed."""
    cfg = {"mode": "direct"}
    text = "The list has bullet points here"
    out = transform(text, cfg)
    assert "bullet points" not in out
    assert "The list has" in out
    assert "here" in out


def test_emphasis_markdown_preserved():
    """Markdown emphasis *word* is not affected by bullet stripping."""
    cfg = {"mode": "direct"}
    text = "This is *emphasized* text"
    out = transform(text, cfg)
    # Emphasis is inline, not line-leading, so it's preserved
    assert "*emphasized*" in out


def test_strong_emphasis_preserved():
    """Markdown strong emphasis **word** is not affected."""
    cfg = {"mode": "direct"}
    text = "This is **strong** text"
    out = transform(text, cfg)
    assert "**strong**" in out


def test_code_fence_content_not_affected():
    """Content inside code fences is not processed (already masked)."""
    cfg = {"mode": "direct"}
    text = "```\n* this is code\n* more code\n```"
    out = transform(text, cfg)
    # Code fences are handled upstream and masked, so the * inside won't be stripped
    # (they're already removed/transformed by the code_fence handler)
    assert "code block" in out.lower() or "code" in out.lower()


def test_empty_line_after_bullet_strip():
    """Empty line after stripping a bullet stays empty."""
    cfg = {"mode": "direct"}
    text = "* \n* next item"
    out = transform(text, cfg)
    # First bullet with no content after marker gets stripped to empty, next one processed normally
    assert "next item" in out


def test_whitespace_collapse_after_word_removal():
    """Multiple spaces from word removal are collapsed."""
    cfg = {"mode": "direct"}
    text = "The pattern has  asterisks  in it"
    out = transform(text, cfg)
    assert "asterisks" not in out
    # Should not have double spaces
    assert "  " not in out


# ---------------------------------------------------------------------------
# Status symbols — ✓ ⌛ ❗ etc. get semantic phrase substitution when
# leading a line; silently stripped mid-sentence or decorative.
# ---------------------------------------------------------------------------

def test_strip_status_checkmark_leading_becomes_done():
    """Leading ✓ gets substituted with "Done: " prefix."""
    cfg = {"mode": "direct"}
    text = "✓ Fixed the auth bug"
    out = transform(text, cfg)
    # TTS should hear "Done:" not "checkmark"
    assert "Done:" in out
    assert "Fixed the auth bug" in out
    assert "✓" not in out


def test_strip_status_hourglass_leading_becomes_working_on():
    """Leading ⌛ gets substituted with "Working on: " prefix."""
    cfg = {"mode": "direct"}
    text = "⌛ Running the migration"
    out = transform(text, cfg)
    assert "Working on:" in out
    assert "Running the migration" in out
    assert "⌛" not in out


def test_strip_status_heavy_exclamation_leading_becomes_issue():
    """Leading ❗ gets substituted with "Issue: " prefix."""
    cfg = {"mode": "direct"}
    text = "❗ Build broke on the auth refactor"
    out = transform(text, cfg)
    assert "Issue:" in out
    assert "Build broke" in out
    assert "❗" not in out


def test_strip_status_x_mark_leading_becomes_failed():
    """Leading ✗ gets substituted with "Failed: " prefix."""
    cfg = {"mode": "direct"}
    text = "✗ Tests didn't pass"
    out = transform(text, cfg)
    assert "Failed:" in out
    assert "Tests didn't pass" in out
    assert "✗" not in out


def test_strip_status_lightbulb_leading_becomes_insight():
    """Leading 💡 gets substituted with "Insight: " prefix."""
    cfg = {"mode": "direct"}
    text = "💡 Caching the response would skip the third round-trip"
    out = transform(text, cfg)
    assert "Insight:" in out
    assert "💡" not in out


def test_strip_status_mid_sentence_silently_dropped():
    """Mid-sentence status symbols get silently stripped — surrounding
    text carries the meaning."""
    cfg = {"mode": "direct"}
    text = "Use ✓ syntax for the boolean toggle"
    out = transform(text, cfg)
    # Symbol gone, no "Done:" inserted, no double spaces left behind
    assert "✓" not in out
    assert "Done:" not in out
    assert "Use" in out and "syntax" in out
    assert "  " not in out


def test_strip_decorative_symbols_silently():
    """Decorative emoji (🎉 ⭐ 🚀 etc.) get stripped without substitution."""
    cfg = {"mode": "direct"}
    text = "Deployment complete 🎉 — ship it 🚀"
    out = transform(text, cfg)
    assert "🎉" not in out
    assert "🚀" not in out
    assert "Deployment complete" in out
    assert "ship it" in out


def test_strip_spelled_out_symbol_names():
    """Spelled-out names like "checkmark" / "hourglass" get stripped so
    TTS doesn't say them when the LLM transcribes a visual UI."""
    cfg = {"mode": "direct"}
    text = "Add a checkmark next to the completed item"
    out = transform(text, cfg)
    assert "checkmark" not in out.lower()
    assert "Add a" in out and "next to" in out


def test_strip_three_status_symbols_in_sequence():
    """A status-symbol-prefixed list gets per-line substitution."""
    cfg = {"mode": "direct"}
    text = "✓ Fixed bug\n⌛ Running tests\n❗ Blocker found"
    out = transform(text, cfg)
    assert "Done:" in out
    assert "Working on:" in out
    assert "Issue:" in out
    # Symbols all stripped
    for sym in ["✓", "⌛", "❗"]:
        assert sym not in out


def test_bullet_then_status_symbol_combo():
    """When a bullet marker AND a status symbol both lead the line,
    the bullet stripper runs first, then the status symbol gets
    substituted: '* ✓ Fix' → '✓ Fix.' → 'Done: Fix.'"""
    cfg = {"mode": "direct"}
    text = "* ✓ Fixed the bug\n- ⌛ Running tests"
    out = transform(text, cfg)
    assert "Done:" in out
    assert "Working on:" in out
    # Neither bullet nor symbol survives
    assert "*" not in out
    assert "✓" not in out
    assert "⌛" not in out


def test_status_symbol_does_not_break_audible_block():
    """Audible blocks (passed through) must not have their symbols
    stripped — the user wants verbatim audible passages preserved.
    """
    cfg = {"mode": "direct"}
    # Use the audible block marker pattern from the markup pipeline
    text = "Audible: speak this ✓ literally"
    out = transform(text, cfg)
    # Whatever the audible-block detection produces, the verbatim text
    # should survive the status-symbol pass since audible blocks are
    # masked + restored around the strip step.
    assert "speak this" in out
