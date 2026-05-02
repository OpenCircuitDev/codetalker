"""Mode A: direct read.

Walks the assistant prose through mistune AST, applies per-element handlers,
runs postprocess regexes (paths, URLs, decorations), filters paragraphs by
the configured content_filter mode, and truncates at boundary.
"""
from __future__ import annotations

import re

import mistune

from claude_code_talker.modes.base import ModeStrategy


URL_RE = re.compile(r"https?://(?:www\.)?([^\s/]+)(?:/\S*)?")
PATH_RE = re.compile(r"\S*[\\/][^\s\\/]+\.\w{1,5}\b")
PATH_RE_FILENAME = re.compile(r"\S*[\\/]([^\s\\/]+\.\w{1,5})\b")
DECO_RE = re.compile(r"[\u2014\u2190-\u21ff\u2500-\u257f\u2600-\u27bf]")
ASCII_RUN_RE = re.compile(r"[\-=*/~_]{3,}")
WS_RE = re.compile(r"[ \t]+")
NEWLINES_RE = re.compile(r"\n{3,}")
INSIGHT_RE = re.compile(r"\u2605\s*Insight[^\r\n]*(?:\n[^\n]*)*?\n[\u2500-\u257f]+", re.DOTALL)


_DEFAULT_ELEMENTS = {
    "heading": True, "code_block": False, "inline_code": True,
    "link": True, "list": True, "blockquote": True,
    "emphasis": True, "table": False, "insight_block": False,
}


class DirectMode(ModeStrategy):
    name = "direct"

    def build(self, prose_entries, tool_uses, todos, cfg):
        if not prose_entries:
            return ""
        md = mistune.create_markdown(renderer=None)
        rendered_parts = [self._render_ast(md(p), cfg) for p in prose_entries]
        text = "\n\n".join(rendered_parts)
        text = self._filter_paragraphs(text, cfg)
        text = self._postprocess(text, cfg)
        text = self._truncate(text, cfg)
        return text

    def _render_ast(self, ast, cfg):
        elem = {**_DEFAULT_ELEMENTS, **(cfg.get("elements") or {})}
        return self._render_node(ast, elem)

    def _render_node(self, node, elem):
        if isinstance(node, list):
            return "".join(self._render_node(n, elem) for n in node)
        if not isinstance(node, dict):
            return ""
        t = node.get("type")
        children = node.get("children", [])
        raw = node.get("raw", "")

        if t == "text":
            return raw
        if t == "heading":
            return (self._render_node(children, elem) + ". ") if elem["heading"] else ""
        if t == "block_code":
            return raw if elem["code_block"] else " code block omitted. "
        if t == "codespan":
            return raw if elem["inline_code"] else ""
        if t == "link":
            return self._render_node(children, elem) if elem["link"] else ""
        if t == "paragraph":
            return self._render_node(children, elem) + "\n\n"
        if t == "list":
            return self._render_node(children, elem) if elem["list"] else ""
        if t == "list_item":
            return self._render_node(children, elem) + ", "
        if t == "block_quote":
            return (self._render_node(children, elem) + " ") if elem["blockquote"] else ""
        if t in ("emphasis", "strong"):
            return self._render_node(children, elem) if elem["emphasis"] else ""
        if t in ("softbreak", "linebreak"):
            return " "
        if t == "thematic_break":
            return "\n\n"
        if t == "table":
            return " table omitted. " if not elem["table"] else self._render_node(children, elem)
        if t in ("block_html", "inline_html"):
            return ""
        if children:
            return self._render_node(children, elem)
        return raw or ""

    def _filter_paragraphs(self, text, cfg):
        fc = cfg.get("content_filter") or {}
        mode = fc.get("mode", "off")
        if mode == "off":
            return text
        if mode == "suppress":
            return ""

        skip_patterns = []
        for p in fc.get("skip_paragraph_patterns") or []:
            try:
                skip_patterns.append(re.compile(p, re.MULTILINE))
            except re.error:
                continue

        skip_starts = [s.lower() for s in fc.get("skip_paragraphs_starting_with") or []]
        keywords = [k.lower() for k in fc.get("speak_keywords") or []]

        kept = []
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            lower = para.lower()
            if any(p.match(para) for p in skip_patterns):
                continue
            if any(lower.startswith(s) for s in skip_starts):
                continue
            if mode == "whitelist" and not any(k in lower for k in keywords):
                continue
            kept.append(para)
        return "\n\n".join(kept)

    def _postprocess(self, text, cfg):
        elements = cfg.get("elements") or {}
        if not elements.get("insight_block", False):
            text = INSIGHT_RE.sub("", text)
        if (cfg.get("urls") or {}).get("shorten_to_host", True):
            text = URL_RE.sub(r"\1", text)
        handling = (cfg.get("paths") or {}).get("handling", "filename")
        if handling == "filename":
            text = PATH_RE_FILENAME.sub(r"\1", text)
        elif handling == "omit":
            text = PATH_RE.sub(" ", text)
        elif handling == "the_file":
            text = PATH_RE.sub(" the file ", text)
        text = ASCII_RUN_RE.sub(" ", text)
        text = DECO_RE.sub(" ", text)
        for r in cfg.get("custom_replacements") or []:
            try:
                text = re.sub(r["pattern"], r["replace"], text)
            except (re.error, KeyError):
                continue
        text = WS_RE.sub(" ", text)
        text = NEWLINES_RE.sub("\n\n", text)
        return text.strip()

    def _truncate(self, text, cfg):
        tc = cfg.get("text") or {}
        if tc.get("no_cap", False):
            return text
        max_chars = int(tc.get("max_chars", 1500))
        if len(text) <= max_chars:
            return text
        snap = tc.get("boundary_snap", "sentence")
        truncated = text[:max_chars]
        floor = int(max_chars * 0.5)
        if snap == "paragraph":
            idx = truncated.rfind("\n\n")
            if idx > floor:
                truncated = truncated[:idx]
        elif snap == "sentence":
            best = -1
            for term in (". ", "? ", "! ", ".\n", "?\n", "!\n"):
                idx = truncated.rfind(term)
                if idx > best:
                    best = idx + 1
            if best > floor:
                truncated = truncated[:best]
        elif snap == "word":
            idx = truncated.rfind(" ")
            if idx > int(max_chars * 0.8):
                truncated = truncated[:idx]
        return truncated.rstrip() + tc.get("truncation_marker", "...")
