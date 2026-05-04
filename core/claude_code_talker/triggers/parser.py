"""Auto-recognize Audible * trigger blocks in assistant prose.

Two formats accepted:
1. Markdown header:  `## Audible <Name>\n<content>` (terminates at next ## or end)
2. Prefix line:      `Audible <Name>: <content>` (single line, terminates at \n)

ALL Audible * tag names are auto-detected — the parser doesn't need a fixed
list. The caller (live mode) filters against the user's enabled tag set so
disabled tags are silently dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_AUDIBLE_PREFIX = "Audible"


@dataclass
class TriggerBlock:
    tag_id: str          # normalized: "audible_summary"
    display_name: str    # original casing: "Audible Summary"
    content: str
    format: str          # "header" | "prefix"
    start_offset: int


def normalize_tag_id(display_name: str) -> str:
    """`Audible Summary` → `audible_summary`. Stable across casings."""
    return display_name.strip().lower().replace(" ", "_").replace("-", "_")


# Markdown header: `## Audible <Name>\n<content>` until next `##` or end-of-string
_HEADER_RE = re.compile(
    r"^##\s+(Audible\s+[A-Za-z][A-Za-z0-9 _-]*?)\s*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# Prefix line: `Audible <Name>: <content>` on a single line
_PREFIX_RE = re.compile(
    r"^(Audible\s+[A-Za-z][A-Za-z0-9 _-]*?):\s*(.+?)$",
    re.MULTILINE | re.IGNORECASE,
)


def _proper_case_audible(s: str) -> str:
    """Normalise display name to title-case 'Audible Foo'."""
    parts = s.strip().split()
    return " ".join([p.capitalize() for p in parts])


def parse_blocks(text: str, enabled_tag_ids: set[str]) -> list[TriggerBlock]:
    """Extract Audible * blocks from text. Filter to enabled_tag_ids. De-dup."""
    if not text:
        return []
    out: list[TriggerBlock] = []
    seen: set[tuple[str, str]] = set()

    def _add(block: TriggerBlock) -> None:
        key = (block.tag_id, block.content[:200])
        if key in seen:
            return
        seen.add(key)
        out.append(block)

    # 1. Markdown headers
    for m in _HEADER_RE.finditer(text):
        display = _proper_case_audible(m.group(1))
        tid = normalize_tag_id(display)
        if tid not in enabled_tag_ids:
            continue
        content = m.group(2).strip()
        if not content:
            continue
        _add(TriggerBlock(tag_id=tid, display_name=display, content=content,
                          format="header", start_offset=m.start()))

    # 2. Prefix lines
    for m in _PREFIX_RE.finditer(text):
        display = _proper_case_audible(m.group(1))
        tid = normalize_tag_id(display)
        if tid not in enabled_tag_ids:
            continue
        content = m.group(2).strip()
        if not content:
            continue
        _add(TriggerBlock(tag_id=tid, display_name=display, content=content,
                          format="prefix", start_offset=m.start()))

    out.sort(key=lambda b: b.start_offset)
    return out
