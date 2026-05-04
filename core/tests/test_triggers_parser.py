"""Tests for triggers.parser — auto-recognize Audible * blocks."""
import pytest
from claude_code_talker.triggers.parser import (
    parse_blocks, TriggerBlock, normalize_tag_id,
)


def test_normalize_tag_id_basic():
    assert normalize_tag_id("Audible Summary") == "audible_summary"
    assert normalize_tag_id("Audible Briefs") == "audible_briefs"
    assert normalize_tag_id("AUDIBLE DETAILS") == "audible_details"


def test_parse_markdown_header_audible_summary():
    text = "Some prose.\n\n## Audible Summary\nI'm restarting PIE clean.\n\nMore prose."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary"})
    assert len(blocks) == 1
    assert blocks[0].tag_id == "audible_summary"
    assert blocks[0].display_name == "Audible Summary"
    assert "restarting PIE" in blocks[0].content
    assert blocks[0].format == "header"


def test_parse_prefix_line_audible_summary():
    text = "Audible summary: I'm restarting PIE clean.\nMore."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary"})
    assert len(blocks) == 1
    assert blocks[0].tag_id == "audible_summary"
    assert "restarting PIE" in blocks[0].content
    assert blocks[0].format == "prefix"


def test_parse_recognizes_arbitrary_audible_tag():
    """Auto-recognition: any ## Audible <X> works without parser update."""
    text = "## Audible Funkadelic\nGroovy narration here."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_funkadelic"})
    assert len(blocks) == 1
    assert blocks[0].tag_id == "audible_funkadelic"
    assert blocks[0].display_name == "Audible Funkadelic"


def test_disabled_tag_filtered():
    text = "## Audible Summary\nA\n\n## Audible Synopsis\nB"
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary"})
    assert len(blocks) == 1
    assert blocks[0].tag_id == "audible_summary"


def test_non_audible_header_ignored():
    text = "## Plan\nNot an Audible block.\n\n## Audible Summary\nThis one is."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary", "audible_plan"})
    assert len(blocks) == 1
    assert blocks[0].tag_id == "audible_summary"


def test_dedup_same_block_twice():
    text = "## Audible Summary\nSame.\n\n## Audible Summary\nSame."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary"})
    assert len(blocks) == 1


def test_multiple_distinct_tags_kept():
    text = "## Audible Summary\nFirst.\n\n## Audible Briefs\nSecond."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary", "audible_briefs"})
    assert len(blocks) == 2


def test_header_terminates_at_next_header():
    text = "## Audible Summary\nFirst block.\n## Audible Briefs\nSecond block."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary", "audible_briefs"})
    first = next(b for b in blocks if b.tag_id == "audible_summary")
    assert "Second block" not in first.content
    assert "First block" in first.content


def test_empty_or_no_match_returns_empty():
    assert parse_blocks("", enabled_tag_ids={"audible_summary"}) == []
    assert parse_blocks("plain text", enabled_tag_ids={"audible_summary"}) == []


def test_case_insensitive_prefix():
    text = "AUDIBLE SUMMARY: case insensitive."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary"})
    assert len(blocks) == 1
    assert "case insensitive" in blocks[0].content


def test_start_offset_is_set():
    """TriggerBlock.start_offset reflects position in source text."""
    text = "Preamble text.\n\n## Audible Summary\nContent here."
    blocks = parse_blocks(text, enabled_tag_ids={"audible_summary"})
    assert len(blocks) == 1
    assert blocks[0].start_offset > 0
