# CCT Phase 26 — Claude Code Markup Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the narrator structure-aware: ten Claude Code markup forms (code fences, inline code, todo updates, plans, audible blocks, system reminders, tool output, subagent dispatches, file paths, long numerals) each get their own treatment row in settings, plus mode-as-presets and per-trigger-tag overrides.

**Architecture:** New `core/claude_code_talker/markup/` package with five files (`forms.py`, `recognizers.py`, `treatment.py`, `pipeline.py`, `describer.py`). `direct.py:_postprocess`, `live.py:_trigger_handler`+`_emit_chunk`, and `event_render.py` swap their ad-hoc text rules for `markup.pipeline.transform(prose, cfg)` / `transform_event(event, cfg)`. Legacy `text.paths.handling` and `elements.code_block` cfg keys fold into the framework via a load-time read shim. Settings UI lands in legacy `/ui/` first as a Markup tab; React dashboard gets a link-out.

**Tech Stack:** Python 3.11+ dataclasses, compiled `re` regexes, PyYAML for cfg, Starlette routes, pytest.

**Reference spec:** [docs/superpowers/specs/2026-05-09-cct-26-markup-awareness-design.md](../specs/2026-05-09-cct-26-markup-awareness-design.md) — read before starting.

**File structure**:
```
core/claude_code_talker/markup/                # NEW package (~600 LOC total)
├── __init__.py
├── forms.py            # FORM_KINDS, Treatment, presets, load_treatments
├── recognizers.py      # detect_<form>(text|event) → list[Span]
├── treatment.py        # apply_treatment(span, treatment, cfg) → str | None
├── pipeline.py         # transform(prose, cfg), transform_event(event, cfg)
└── describer.py        # human-language renderers

core/claude_code_talker/
├── modes/direct.py     # MODIFY — _postprocess uses markup.pipeline.transform
├── modes/live.py       # MODIFY — _trigger_handler + _emit_chunk wired
├── event_render.py     # MODIFY — Bash/tool output via describer
├── triggers/tags.py    # MODIFY — Tag.markup_overrides field
└── api.py              # MODIFY — GET/PUT /api/markup/config

static/index.html       # MODIFY — Markup tab button + pane
static/app.js           # MODIFY — TAB_RENDERERS.markup with per-form rows
core/claude_code_talker/webui/src/components/SessionControls.tsx  # MODIFY — link-out

core/tests/
├── test_markup_recognizers.py   # NEW — 12 tests
├── test_markup_treatment.py     # NEW — 8 tests
├── test_markup_pipeline.py      # NEW — 7 tests
└── test_markup_api.py           # NEW — 3 tests
```

---

## Task 1: Forms catalog + Treatment dataclass + presets (TDD)

**Files:**
- Create: `core/claude_code_talker/markup/__init__.py`
- Create: `core/claude_code_talker/markup/forms.py`
- Create: `core/tests/test_markup_forms.py`

- [ ] **Step 1: Write failing tests**

Create `core/tests/test_markup_forms.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest core/tests/test_markup_forms.py -v`
Expected: all FAIL with `ModuleNotFoundError: claude_code_talker.markup`.

- [ ] **Step 3: Implement forms.py**

Create `core/claude_code_talker/markup/__init__.py` (empty).

Create `core/claude_code_talker/markup/forms.py`:

```python
"""Phase 26 — markup form catalog, Treatment dataclass, mode presets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Treatment:
    kind: str
    params: dict = field(default_factory=dict)


FORM_KINDS: dict[str, set[str]] = {
    "code_fence":         {"skip", "describe", "read"},
    "inline_code":        {"skip", "identifier_only", "read"},
    "todo_update":        {"skip", "count_only", "itemize", "read"},
    "plan_block":         {"skip", "summarize", "read"},
    "audible_block":      {"speak"},
    "system_reminder":    {"skip", "log_silently"},
    "tool_output":        {"skip", "describe", "read"},
    "subagent_dispatch":  {"skip", "announce", "describe"},
    "file_path":          {"skip", "filename", "describe", "read"},
    "long_numeral":       {"skip", "describe", "read"},
}


PRESETS: dict[str, dict[str, Treatment]] = {
    "brief": {
        "code_fence":        Treatment("skip"),
        "inline_code":       Treatment("identifier_only"),
        "todo_update":       Treatment("count_only"),
        "plan_block":        Treatment("summarize", {"max_words": 60}),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("describe"),
        "subagent_dispatch": Treatment("announce"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
    "direct": {
        "code_fence":        Treatment("describe"),
        "inline_code":       Treatment("read"),
        "todo_update":       Treatment("itemize", {"max_items": 5}),
        "plan_block":        Treatment("read"),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("read"),
        "subagent_dispatch": Treatment("describe"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
    "live": {
        "code_fence":        Treatment("describe"),
        "inline_code":       Treatment("identifier_only"),
        "todo_update":       Treatment("itemize", {"max_items": 3}),
        "plan_block":        Treatment("summarize", {"max_words": 80}),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("describe"),
        "subagent_dispatch": Treatment("describe"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
    "trigger": {
        "code_fence":        Treatment("skip"),
        "inline_code":       Treatment("identifier_only"),
        "todo_update":       Treatment("skip"),
        "plan_block":        Treatment("skip"),
        "audible_block":     Treatment("speak"),
        "system_reminder":   Treatment("skip"),
        "tool_output":       Treatment("skip"),
        "subagent_dispatch": Treatment("skip"),
        "file_path":         Treatment("filename"),
        "long_numeral":      Treatment("describe"),
    },
}


def validate_treatment(form: str, t: Treatment) -> None:
    if form not in FORM_KINDS:
        raise ValueError(f"unknown form: {form}")
    if t.kind not in FORM_KINDS[form]:
        raise ValueError(f"kind {t.kind!r} not allowed for {form}")


def preset_for_mode(mode: str) -> dict[str, Treatment]:
    return PRESETS.get(mode, PRESETS["direct"])


def load_treatments(cfg: dict[str, Any]) -> dict[str, Treatment]:
    mode = (cfg.get("mode") or "direct").lower()
    base = dict(preset_for_mode(mode))
    user = (cfg.get("markup") or {})
    for form in FORM_KINDS:
        node = user.get(form)
        if not isinstance(node, dict):
            continue
        kind = node.get("kind")
        if kind is None:
            continue
        params = node.get("params") or {}
        candidate = Treatment(kind=str(kind), params=dict(params))
        try:
            validate_treatment(form, candidate)
        except ValueError:
            continue  # silently fall back to preset
        base[form] = candidate
    return base
```

- [ ] **Step 4: Run tests pass**

Run: `pytest core/tests/test_markup_forms.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/markup/__init__.py core/claude_code_talker/markup/forms.py core/tests/test_markup_forms.py
git commit -m "feat(markup): forms catalog + Treatment + mode presets (Phase 26 Task 1)"
```

---

## Task 2: Recognizers — prose-only forms (TDD)

**Files:**
- Create: `core/claude_code_talker/markup/recognizers.py`
- Create: `core/tests/test_markup_recognizers.py`

- [ ] **Step 1: Write failing tests for prose recognizers**

```python
"""Phase 26 — markup.recognizers tests (prose-only forms)."""
from __future__ import annotations

from claude_code_talker.markup.recognizers import (
    Span,
    detect_audible_block,
    detect_code_fence,
    detect_file_path,
    detect_inline_code,
    detect_long_numeral,
    detect_plan_block,
    detect_system_reminder,
)


def test_detect_code_fence_finds_triple_backticks():
    text = "before\n```python\nprint('x')\nprint('y')\n```\nafter"
    spans = detect_code_fence(text)
    assert len(spans) == 1
    assert spans[0].form == "code_fence"
    assert spans[0].parsed["language"] == "python"
    assert spans[0].parsed["line_count"] == 2


def test_detect_code_fence_no_language():
    text = "```\nfoo\n```"
    spans = detect_code_fence(text)
    assert spans[0].parsed["language"] == ""


def test_detect_inline_code_marks_identifier():
    text = "Call `foo_bar` then `not an identifier`."
    spans = detect_inline_code(text)
    assert len(spans) == 2
    assert spans[0].parsed["is_identifier"] is True
    assert spans[1].parsed["is_identifier"] is False


def test_detect_inline_code_dotted_identifier():
    text = "Use `module.func` directly."
    spans = detect_inline_code(text)
    assert spans[0].parsed["is_identifier"] is True


def test_detect_system_reminder_html_form():
    text = "<system-reminder>do this</system-reminder> rest"
    spans = detect_system_reminder(text)
    assert len(spans) == 1
    assert spans[0].form == "system_reminder"


def test_detect_file_path_basic():
    text = "Open `src/foo/bar.py:42` to see it."
    spans = detect_file_path(text)
    assert any(s.form == "file_path" for s in spans)


def test_detect_long_numeral_seven_digits():
    text = "Order 1234567 was placed."
    spans = detect_long_numeral(text)
    assert len(spans) == 1
    assert spans[0].text == "1234567"


def test_detect_long_numeral_ignores_short():
    text = "Order 12345 was placed."
    assert detect_long_numeral(text) == []


def test_detect_plan_block_header():
    text = "Intro\n\n## Plan\nstep 1\nstep 2"
    spans = detect_plan_block(text)
    assert len(spans) == 1


def test_detect_audible_block_passthrough():
    text = "## Audible Summary\nHello there.\n\nMore prose."
    spans = detect_audible_block(text)
    assert len(spans) == 1
    assert "Hello there" in spans[0].text
```

- [ ] **Step 2: Implement prose recognizers**

Create `core/claude_code_talker/markup/recognizers.py`:

```python
"""Phase 26 — recognizers for the ten markup forms."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Span:
    form: str
    start: int
    end: int
    text: str
    parsed: dict[str, Any] = field(default_factory=dict)


_RE_CODE_FENCE = re.compile(r"^```([^\n]*)\n([\s\S]*?)\n```", re.MULTILINE)
_RE_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_RE_IDENTIFIER = re.compile(r"^[A-Za-z_][\w.]*$")
_RE_SYSTEM_REMINDER = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")
_RE_FILE_PATH = re.compile(
    r"`?([\w./\\-]+\.[A-Za-z0-9]{1,8})(?::\d+)?`?"
)
_RE_LONG_NUMERAL = re.compile(r"\b\d{7,}\b")
_RE_PLAN_HEADER = re.compile(r"^##\s+Plan\s*\n([\s\S]*?)(?=\n##\s|\Z)", re.MULTILINE)
_RE_AUDIBLE_HEADER = re.compile(
    r"^##\s+Audible\s+([A-Za-z][\w-]*)\s*\n([\s\S]*?)(?=\n##\s|\Z)",
    re.MULTILINE,
)


def detect_code_fence(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_CODE_FENCE.finditer(text):
        lang = (m.group(1) or "").strip()
        body = m.group(2) or ""
        out.append(Span(
            form="code_fence",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"language": lang, "line_count": body.count("\n") + (0 if not body else 1)},
        ))
    return out


def detect_inline_code(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_INLINE_CODE.finditer(text):
        body = m.group(1)
        out.append(Span(
            form="inline_code",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"is_identifier": bool(_RE_IDENTIFIER.match(body))},
        ))
    return out


def detect_system_reminder(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_SYSTEM_REMINDER.finditer(text):
        out.append(Span("system_reminder", m.start(), m.end(), m.group(0)))
    return out


def detect_file_path(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_FILE_PATH.finditer(text):
        path = m.group(1)
        if "/" not in path and "\\" not in path:
            continue  # require a directory separator to avoid false positives like "x.y"
        out.append(Span(
            form="file_path",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"path": path},
        ))
    return out


def detect_long_numeral(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_LONG_NUMERAL.finditer(text):
        out.append(Span("long_numeral", m.start(), m.end(), m.group(0)))
    return out


def detect_plan_block(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_PLAN_HEADER.finditer(text):
        out.append(Span(
            form="plan_block",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"body": m.group(1)},
        ))
    return out


def detect_audible_block(text: str) -> list[Span]:
    out: list[Span] = []
    for m in _RE_AUDIBLE_HEADER.finditer(text):
        out.append(Span(
            form="audible_block",
            start=m.start(), end=m.end(),
            text=m.group(0),
            parsed={"tag": m.group(1).lower(), "body": m.group(2)},
        ))
    return out
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_markup_recognizers.py -v`
Expected: 10 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/markup/recognizers.py core/tests/test_markup_recognizers.py
git commit -m "feat(markup): prose recognizers for 7 forms (Phase 26 Task 2)"
```

---

## Task 3: Recognizers — event-driven forms (TDD)

**Files:**
- Modify: `core/claude_code_talker/markup/recognizers.py`
- Modify: `core/tests/test_markup_recognizers.py`

- [ ] **Step 1: Add failing tests for event recognizers**

Append to `core/tests/test_markup_recognizers.py`:

```python
def test_detect_todo_update_from_tool_event():
    from claude_code_talker.markup.recognizers import detect_todo_update
    event = {
        "kind": "tool_use",
        "name": "TodoWrite",
        "input": {"todos": [{"content": "a", "status": "completed"}, {"content": "b", "status": "in_progress"}]},
    }
    spans = detect_todo_update(event)
    assert len(spans) == 1
    assert spans[0].parsed["completed"] == 1
    assert spans[0].parsed["in_progress"] == 1


def test_detect_todo_update_ignores_non_todo_events():
    from claude_code_talker.markup.recognizers import detect_todo_update
    event = {"kind": "tool_use", "name": "Bash", "input": {}}
    assert detect_todo_update(event) == []


def test_detect_tool_output_post_event():
    from claude_code_talker.markup.recognizers import detect_tool_output
    event = {
        "kind": "post_tool",
        "name": "Bash",
        "exit_code": 0,
        "stdout": "line1\nline2\nline3\n",
    }
    spans = detect_tool_output(event)
    assert len(spans) == 1
    assert spans[0].parsed["tool_name"] == "Bash"
    assert spans[0].parsed["line_count"] == 3
    assert spans[0].parsed["exit_code"] == 0


def test_detect_subagent_dispatch_pre_and_post():
    from claude_code_talker.markup.recognizers import detect_subagent_dispatch
    pre = {"kind": "tool_use", "name": "Task", "id": "abc", "input": {"subagent_type": "Explore"}}
    post = {"kind": "post_tool", "name": "Task", "id": "abc"}
    assert detect_subagent_dispatch(pre)[0].parsed["phase"] == "pre"
    assert detect_subagent_dispatch(post)[0].parsed["phase"] == "post"
```

- [ ] **Step 2: Implement event recognizers**

Append to `core/claude_code_talker/markup/recognizers.py`:

```python
def detect_todo_update(event: dict[str, Any]) -> list[Span]:
    if event.get("kind") != "tool_use" or event.get("name") != "TodoWrite":
        return []
    todos = (event.get("input") or {}).get("todos") or []
    counts = {"completed": 0, "in_progress": 0, "pending": 0}
    for t in todos:
        s = (t or {}).get("status") or "pending"
        counts[s] = counts.get(s, 0) + 1
    return [Span(
        form="todo_update",
        start=0, end=0, text="",
        parsed={"todos": todos, **counts},
    )]


def detect_tool_output(event: dict[str, Any]) -> list[Span]:
    if event.get("kind") != "post_tool":
        return []
    name = event.get("name") or ""
    if name == "Task":
        return []  # handled by detect_subagent_dispatch
    stdout = event.get("stdout") or ""
    return [Span(
        form="tool_output",
        start=0, end=0, text=stdout,
        parsed={
            "tool_name": name,
            "exit_code": event.get("exit_code"),
            "line_count": stdout.count("\n"),
        },
    )]


def detect_subagent_dispatch(event: dict[str, Any]) -> list[Span]:
    name = event.get("name") or ""
    kind = event.get("kind") or ""
    if name != "Task":
        return []
    phase = "pre" if kind == "tool_use" else "post" if kind == "post_tool" else None
    if phase is None:
        return []
    parsed: dict[str, Any] = {"phase": phase, "tool_use_id": event.get("id")}
    if phase == "pre":
        parsed["subagent_type"] = (event.get("input") or {}).get("subagent_type")
    return [Span("subagent_dispatch", 0, 0, "", parsed=parsed)]
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_markup_recognizers.py -v`
Expected: 14 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/markup/recognizers.py core/tests/test_markup_recognizers.py
git commit -m "feat(markup): event recognizers — todo_update, tool_output, subagent_dispatch (Phase 26 Task 3)"
```

---

## Task 4: Treatment dispatch + describer (TDD)

**Files:**
- Create: `core/claude_code_talker/markup/treatment.py`
- Create: `core/claude_code_talker/markup/describer.py`
- Create: `core/tests/test_markup_treatment.py`

- [ ] **Step 1: Write failing tests**

```python
"""Phase 26 — treatment dispatch tests."""
from __future__ import annotations

from claude_code_talker.markup.forms import Treatment
from claude_code_talker.markup.recognizers import Span
from claude_code_talker.markup.treatment import apply_treatment


def test_apply_skip_returns_none():
    span = Span("code_fence", 0, 5, "```\nx\n```", parsed={"language": "", "line_count": 1})
    assert apply_treatment(span, Treatment("skip"), {}) is None


def test_apply_describe_code_fence():
    span = Span("code_fence", 0, 5, "```py\na\nb\nc\n```", parsed={"language": "py", "line_count": 3})
    out = apply_treatment(span, Treatment("describe"), {})
    assert "code" in out.lower()
    assert "3" in out or "three" in out.lower()


def test_apply_inline_code_identifier_only_keeps_identifier():
    span = Span("inline_code", 0, 8, "`foo_bar`", parsed={"is_identifier": True})
    out = apply_treatment(span, Treatment("identifier_only"), {})
    assert "foo_bar" in out


def test_apply_inline_code_identifier_only_drops_non_identifier():
    span = Span("inline_code", 0, 8, "`not code`", parsed={"is_identifier": False})
    assert apply_treatment(span, Treatment("identifier_only"), {}) == ""


def test_apply_file_path_filename():
    span = Span("file_path", 0, 0, "src/foo/bar.py:42", parsed={"path": "src/foo/bar.py:42"})
    out = apply_treatment(span, Treatment("filename"), {})
    assert "bar.py" in out


def test_apply_long_numeral_describe():
    span = Span("long_numeral", 0, 0, "1234567")
    out = apply_treatment(span, Treatment("describe"), {})
    assert "long" in out.lower() or "number" in out.lower()


def test_apply_todo_update_count_only():
    span = Span("todo_update", 0, 0, "", parsed={"completed": 3, "in_progress": 1, "pending": 2, "todos": []})
    out = apply_treatment(span, Treatment("count_only"), {})
    assert "3" in out and "1" in out


def test_apply_unknown_kind_returns_none():
    span = Span("code_fence", 0, 5, "```\nx\n```", parsed={"language": "", "line_count": 1})
    assert apply_treatment(span, Treatment("unknown"), {}) is None
```

- [ ] **Step 2: Implement describer + treatment**

Create `core/claude_code_talker/markup/describer.py`:

```python
"""Phase 26 — human-language renderers for markup spans."""
from __future__ import annotations

import os


def describe_code_fence(language: str, line_count: int) -> str:
    if line_count <= 1:
        size = "a one-line"
    elif line_count < 10:
        size = "a short"
    elif line_count < 50:
        size = "a medium"
    else:
        size = "a long"
    lang = f"{language} " if language else ""
    return f"{size} {lang}code block"


def describe_long_numeral(_text: str) -> str:
    return "a long number"


def describe_file_path(path: str, mode: str = "filename") -> str:
    base = os.path.basename(path.split(":", 1)[0])
    if mode == "filename":
        return base
    return f"the file {base}"


def describe_tool_output(tool: str, exit_code: int | None, line_count: int) -> str:
    state = "succeeded" if exit_code == 0 else f"exited with code {exit_code}" if exit_code else "ran"
    return f"{tool} {state} with {line_count} lines of output"


def describe_subagent(phase: str, subagent_type: str | None) -> str:
    label = subagent_type or "subagent"
    if phase == "pre":
        return f"dispatching {label}"
    return f"{label} returned"
```

Create `core/claude_code_talker/markup/treatment.py`:

```python
"""Phase 26 — apply a Treatment to a Span, returning the replacement text or None to delete."""
from __future__ import annotations

from typing import Any

from .describer import (
    describe_code_fence,
    describe_file_path,
    describe_long_numeral,
    describe_subagent,
    describe_tool_output,
)
from .forms import Treatment
from .recognizers import Span


def apply_treatment(span: Span, t: Treatment, cfg: dict[str, Any]) -> str | None:
    """Return replacement text for the span, or None to remove it entirely."""
    k = t.kind
    if k == "skip" or k == "log_silently":
        return None
    if k == "speak":
        return span.text  # passthrough; caller routes to TTS

    f = span.form
    if f == "code_fence":
        if k == "describe":
            return describe_code_fence(span.parsed.get("language", ""), span.parsed.get("line_count", 0))
        if k == "read":
            return span.text
    elif f == "inline_code":
        if k == "identifier_only":
            return span.text.strip("`") if span.parsed.get("is_identifier") else ""
        if k == "read":
            return span.text.strip("`")
    elif f == "todo_update":
        c = span.parsed.get("completed", 0)
        ip = span.parsed.get("in_progress", 0)
        p = span.parsed.get("pending", 0)
        if k == "count_only":
            return f"{c} done, {ip} in progress, {p} pending"
        if k == "itemize":
            limit = int((t.params or {}).get("max_items") or 5)
            todos = span.parsed.get("todos") or []
            items = []
            for todo in todos[:limit]:
                items.append(f"{todo.get('status', 'pending')}: {todo.get('content', '')}")
            return "; ".join(items)
        if k == "read":
            return ", ".join(t.get("content", "") for t in span.parsed.get("todos") or [])
    elif f == "plan_block":
        body = (span.parsed.get("body") or "").strip()
        if k == "summarize":
            limit = int((t.params or {}).get("max_words") or 60)
            words = body.split()
            return " ".join(words[:limit]) + ("…" if len(words) > limit else "")
        if k == "read":
            return body
    elif f == "system_reminder":
        return None
    elif f == "tool_output":
        if k == "describe":
            return describe_tool_output(
                span.parsed.get("tool_name", ""),
                span.parsed.get("exit_code"),
                span.parsed.get("line_count", 0),
            )
        if k == "read":
            return span.text
    elif f == "subagent_dispatch":
        phase = span.parsed.get("phase", "pre")
        st = span.parsed.get("subagent_type")
        if k == "announce":
            return f"dispatching {st or 'subagent'}" if phase == "pre" else ""
        if k == "describe":
            return describe_subagent(phase, st)
    elif f == "file_path":
        path = span.parsed.get("path") or span.text
        if k == "filename":
            return describe_file_path(path, "filename")
        if k == "describe":
            return describe_file_path(path, "describe")
        if k == "read":
            return path
    elif f == "long_numeral":
        if k == "describe":
            return describe_long_numeral(span.text)
        if k == "read":
            return span.text
    elif f == "audible_block":
        return span.text  # passthrough; trigger parser owns dispatch

    return None
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_markup_treatment.py -v`
Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/markup/treatment.py core/claude_code_talker/markup/describer.py core/tests/test_markup_treatment.py
git commit -m "feat(markup): treatment dispatch + describer (Phase 26 Task 4)"
```

---

## Task 5: Pipeline assembly (TDD)

**Files:**
- Create: `core/claude_code_talker/markup/pipeline.py`
- Create: `core/tests/test_markup_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

```python
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
```

- [ ] **Step 2: Implement pipeline**

Create `core/claude_code_talker/markup/pipeline.py`:

```python
"""Phase 26 — single-entry transform for prose + event streams."""
from __future__ import annotations

import re
from typing import Any

from .forms import Treatment, load_treatments
from .recognizers import (
    Span,
    detect_audible_block,
    detect_code_fence,
    detect_file_path,
    detect_inline_code,
    detect_long_numeral,
    detect_plan_block,
    detect_subagent_dispatch,
    detect_system_reminder,
    detect_todo_update,
    detect_tool_output,
)
from .treatment import apply_treatment


_BLOCK_DETECTORS = (
    ("audible_block", detect_audible_block),
    ("system_reminder", detect_system_reminder),
    ("code_fence", detect_code_fence),
    ("plan_block", detect_plan_block),
)
_SPAN_DETECTORS = (
    ("inline_code", detect_inline_code),
    ("file_path", detect_file_path),
    ("long_numeral", detect_long_numeral),
)


def _replace(text: str, spans: list[tuple[Span, str | None]]) -> str:
    if not spans:
        return text
    spans = sorted(spans, key=lambda x: x[0].start, reverse=True)
    out = text
    for span, replacement in spans:
        out = out[:span.start] + (replacement if replacement is not None else "") + out[span.end:]
    return out


def _audible_passthrough(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Pull audible blocks out of `text`, returning text-with-placeholders + list of (start, end, original)."""
    blocks = detect_audible_block(text)
    if not blocks:
        return text, []
    holes: list[tuple[int, int, str]] = []
    placeholders: list[tuple[int, int, str]] = []
    for i, b in enumerate(blocks):
        token = f"\x00AUDIBLE{i}\x00"
        holes.append((b.start, b.end, b.text))
        placeholders.append((b.start, b.end, token))
    out = text
    for start, end, token in sorted(placeholders, key=lambda x: x[0], reverse=True):
        out = out[:start] + token + out[end:]
    return out, [(idx, original) for idx, (_, _, original) in enumerate(holes)]


def _restore_audible(text: str, holes: list[tuple[int, str]]) -> str:
    for idx, original in holes:
        text = text.replace(f"\x00AUDIBLE{idx}\x00", original)
    return text


def transform(prose: str, cfg: dict[str, Any]) -> str:
    if not prose:
        return prose
    treatments = load_treatments(cfg)

    masked, holes = _audible_passthrough(prose)

    block_spans: list[tuple[Span, str | None]] = []
    for form, detector in _BLOCK_DETECTORS:
        if form == "audible_block":
            continue
        for span in detector(masked):
            replacement = apply_treatment(span, treatments[form], cfg)
            block_spans.append((span, replacement))
    out = _replace(masked, block_spans)

    span_replacements: list[tuple[Span, str | None]] = []
    for form, detector in _SPAN_DETECTORS:
        for span in detector(out):
            replacement = apply_treatment(span, treatments[form], cfg)
            span_replacements.append((span, replacement))
    out = _replace(out, span_replacements)

    out = _restore_audible(out, holes)

    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out


def transform_event(event: dict[str, Any], cfg: dict[str, Any]) -> str | None:
    treatments = load_treatments(cfg)
    if event.get("name") == "TodoWrite" and event.get("kind") == "tool_use":
        spans = detect_todo_update(event)
        if spans:
            return apply_treatment(spans[0], treatments["todo_update"], cfg)
    if event.get("name") == "Task":
        spans = detect_subagent_dispatch(event)
        if spans:
            return apply_treatment(spans[0], treatments["subagent_dispatch"], cfg)
    if event.get("kind") == "post_tool":
        spans = detect_tool_output(event)
        if spans:
            return apply_treatment(spans[0], treatments["tool_output"], cfg)
    return None
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_markup_pipeline.py -v`
Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/markup/pipeline.py core/tests/test_markup_pipeline.py
git commit -m "feat(markup): pipeline assembly with audible passthrough (Phase 26 Task 5)"
```

---

## Task 6: Wire into modes/direct.py

**Files:**
- Modify: `core/claude_code_talker/modes/direct.py`
- Modify: `core/tests/test_modes_direct.py`

- [ ] **Step 1: Locate `_postprocess` and identify legacy text-rule code paths**

Run: `grep -n "_postprocess\|paths.handling\|elements.code_block" core/claude_code_talker/modes/direct.py`

- [ ] **Step 2: Replace the relevant section with `markup.pipeline.transform`**

In `direct.py`, in the function that prepares prose for TTS (typically `_postprocess(text, cfg)` or its caller), replace the body that strips code fences / mangles paths / handles long numerals with:

```python
from claude_code_talker.markup.pipeline import transform as _markup_transform

def _postprocess(text: str, cfg: dict) -> str:
    return _markup_transform(text, cfg)
```

Keep any pre-existing TTS-only steps (like inserting pause tokens) AFTER the markup transform.

- [ ] **Step 3: Update existing test_modes_direct.py expectations**

Some legacy tests may assert specific text that the new pipeline still produces. Run them first to identify failures.

Run: `pytest core/tests/test_modes_direct.py -v`

For any failure where the new output is *equivalent* (e.g., legacy "the file foo.py" vs. new "foo.py"), update the test assertion. For any genuinely-different behavior, document the change in the test comment.

- [ ] **Step 4: All direct mode tests pass**

Run: `pytest core/tests/test_modes_direct.py core/tests/test_markup_pipeline.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/modes/direct.py core/tests/test_modes_direct.py
git commit -m "feat(direct): swap _postprocess for markup.pipeline.transform (Phase 26 Task 6)"
```

---

## Task 7: Wire into modes/live.py

**Files:**
- Modify: `core/claude_code_talker/modes/live.py`

- [ ] **Step 1: Find `_trigger_handler` and `_emit_chunk`**

Run: `grep -n "_trigger_handler\|_emit_chunk" core/claude_code_talker/modes/live.py`

- [ ] **Step 2: In `_trigger_handler`, after composing the cfg with any tag overrides, run the body through `transform_for_live`**

Implement transform_for_live as a thin shim in `pipeline.py`:

```python
def transform_for_live(prose: str, cfg: dict, tag_overrides: dict | None = None) -> str:
    if tag_overrides:
        markup = dict(cfg.get("markup") or {})
        for form, override in (tag_overrides or {}).items():
            existing = dict(markup.get(form) or {})
            existing.update(override)
            markup[form] = existing
        cfg = {**cfg, "markup": markup}
    return transform(prose, cfg)
```

- [ ] **Step 3: In `_emit_chunk`, replace any inline path/code-fence munging with `transform_for_live(chunk, cfg)`**

- [ ] **Step 4: Run live mode tests**

Run: `pytest core/tests/test_modes_live*.py -v`
Update failing assertions to match the new (richer) output.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/modes/live.py core/claude_code_talker/markup/pipeline.py
git commit -m "feat(live): _trigger_handler + _emit_chunk via markup.pipeline (Phase 26 Task 7)"
```

---

## Task 8: Wire into event_render.py

**Files:**
- Modify: `core/claude_code_talker/event_render.py`

- [ ] **Step 1: Find Bash post-tool render path**

Run: `grep -n "summarize_tool_input\|stdout\|exit_code" core/claude_code_talker/event_render.py`

- [ ] **Step 2: For Bash post-tool events, route through markup.pipeline.transform_event**

Replace the ad-hoc summary with:

```python
from claude_code_talker.markup.pipeline import transform_event

# inside the Bash post-tool branch:
narration = transform_event(event_dict, cfg) or ""
if not narration:
    return None
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_event_render*.py -v`

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/event_render.py
git commit -m "feat(event_render): tool_output via markup describer (Phase 26 Task 8)"
```

---

## Task 9: REST endpoints GET/PUT /api/markup/config (TDD)

**Files:**
- Modify: `core/claude_code_talker/api.py`
- Create: `core/tests/test_markup_api.py`

- [ ] **Step 1: Write failing API tests**

```python
"""Phase 26 — markup REST endpoints."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from claude_code_talker.server import build_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_TALKER_HOME", str(tmp_path))
    app = build_app()
    return TestClient(app)


def test_get_markup_config_returns_presets_for_default_mode(client):
    r = client.get("/api/markup/config")
    assert r.status_code == 200
    data = r.json()
    assert "code_fence" in data
    assert data["code_fence"]["kind"] in {"skip", "describe", "read"}


def test_put_markup_config_accepts_valid_kind(client):
    r = client.put("/api/markup/config", json={"code_fence": {"kind": "skip"}})
    assert r.status_code == 200


def test_put_markup_config_rejects_invalid_kind(client):
    r = client.put("/api/markup/config", json={"code_fence": {"kind": "bogus"}})
    assert r.status_code == 400
```

- [ ] **Step 2: Implement endpoints in api.py**

Add (next to existing config routes):

```python
from .markup.forms import FORM_KINDS, validate_treatment, Treatment, load_treatments

async def markup_config_get(request: Request) -> Response:
    cfg = state.cfg.snapshot()
    treatments = load_treatments(cfg)
    body = {form: {"kind": t.kind, "params": t.params} for form, t in treatments.items()}
    return JSONResponse(body)

async def markup_config_put(request: Request) -> Response:
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "expected object"}, status_code=400)
    for form, node in body.items():
        if form not in FORM_KINDS:
            return JSONResponse({"error": f"unknown form: {form}"}, status_code=400)
        if not isinstance(node, dict):
            return JSONResponse({"error": f"{form}: expected object"}, status_code=400)
        kind = node.get("kind")
        if kind is None:
            continue
        try:
            validate_treatment(form, Treatment(kind=str(kind), params=dict(node.get("params") or {})))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    state.cfg.update_keypath("markup", body)
    return JSONResponse({"ok": True})


# Register routes
routes.append(Route("/api/markup/config", markup_config_get, methods=["GET"]))
routes.append(Route("/api/markup/config", markup_config_put, methods=["PUT"]))
```

- [ ] **Step 3: Tests pass**

Run: `pytest core/tests/test_markup_api.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/api.py core/tests/test_markup_api.py
git commit -m "feat(api): GET/PUT /api/markup/config (Phase 26 Task 9)"
```

---

## Task 10: Tag schema extension

**Files:**
- Modify: `core/claude_code_talker/triggers/tags.py`
- Modify: `core/tests/test_tags.py` (if exists) or create `core/tests/test_tag_markup_overrides.py`

- [ ] **Step 1: Add `markup_overrides` field to Tag**

In `tags.py`:

```python
@dataclass(frozen=True)
class Tag:
    # ... existing fields ...
    markup_overrides: dict = field(default_factory=dict)
```

Update `from_cfg` to read `markup_overrides` if present (silently drop if missing — backward compat).

- [ ] **Step 2: Update `live.py` to pass `tag.markup_overrides` into `transform_for_live`**

- [ ] **Step 3: Test**

```python
def test_tag_with_markup_overrides_applies_during_live_dispatch():
    from claude_code_talker.triggers.tags import Tag
    from claude_code_talker.markup.pipeline import transform_for_live
    tag = Tag(name="audible_plan_entry", markup_overrides={"plan_block": {"kind": "read"}})
    cfg = {"mode": "brief", "markup": {"plan_block": {"kind": "skip"}}}
    body = "## Plan\nstep one\nstep two"
    out = transform_for_live(body, cfg, tag.markup_overrides)
    assert "step one" in out
```

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/triggers/tags.py core/claude_code_talker/modes/live.py core/tests/test_tag_markup_overrides.py
git commit -m "feat(triggers): Tag.markup_overrides for per-tag treatment override (Phase 26 Task 10)"
```

---

## Task 11: Legacy UI Markup tab

**Files:**
- Modify: `core/claude_code_talker/static/index.html`
- Modify: `core/claude_code_talker/static/app.js`

- [ ] **Step 1: Add Markup tab button to index.html**

After existing tab buttons:

```html
<button class="tab" data-tab="markup">Markup</button>
```

Add matching pane:

```html
<div class="pane hidden" data-pane="markup">
  <div id="markup-rows"></div>
</div>
```

- [ ] **Step 2: Add `TAB_RENDERERS.markup` to app.js**

```javascript
TAB_RENDERERS.markup = async function(pane, s, cfg) {
  const r = await fetch("/api/markup/config");
  const data = await r.json();
  const rows = [];
  for (const form of Object.keys(data)) {
    const current = data[form];
    const row = document.createElement("div");
    row.className = "markup-row";
    row.innerHTML = `<label><strong>${form}</strong></label>`;
    const select = document.createElement("select");
    const allowed = MARKUP_FORM_KINDS[form] || [];
    for (const k of allowed) {
      const opt = document.createElement("option");
      opt.value = k; opt.textContent = k;
      if (k === current.kind) opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", async () => {
      await fetch("/api/markup/config", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({[form]: {kind: select.value}}),
      });
    });
    row.appendChild(select);
    rows.push(row);
  }
  const container = pane.querySelector("#markup-rows");
  container.innerHTML = "";
  rows.forEach(r => container.appendChild(r));
};

const MARKUP_FORM_KINDS = {
  code_fence: ["skip", "describe", "read"],
  inline_code: ["skip", "identifier_only", "read"],
  todo_update: ["skip", "count_only", "itemize", "read"],
  plan_block: ["skip", "summarize", "read"],
  audible_block: ["speak"],
  system_reminder: ["skip", "log_silently"],
  tool_output: ["skip", "describe", "read"],
  subagent_dispatch: ["skip", "announce", "describe"],
  file_path: ["skip", "filename", "describe", "read"],
  long_numeral: ["skip", "describe", "read"],
};
```

- [ ] **Step 3: Manual smoke test**

Start daemon. Open `http://127.0.0.1:17832/ui/`, click Markup tab, change `code_fence` to `skip`, verify the PUT lands in daemon logs.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/static/index.html core/claude_code_talker/static/app.js
git commit -m "feat(ui): legacy /ui/ Markup tab with per-form rows (Phase 26 Task 11)"
```

---

## Task 12: React dashboard link-out

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/SessionControls.tsx`

- [ ] **Step 1: Add a one-line link-out**

```tsx
<a href="/ui/#markup" target="_blank" rel="noopener" className="text-xs text-cyan-400 hover:underline">
  Markup settings →
</a>
```

- [ ] **Step 2: Build and verify**

Run: `cd core/claude_code_talker/webui && npm run build`

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/components/SessionControls.tsx
git commit -m "feat(webui): SessionControls link-out to /ui/#markup (Phase 26 Task 12)"
```

---

## Task 13: Migration shim for legacy cfg keys

**Files:**
- Modify: `core/claude_code_talker/markup/forms.py` (extend `load_treatments`)

- [ ] **Step 1: Add a compat-read inside `load_treatments`**

Before returning, check legacy keys:

```python
text_cfg = cfg.get("text") or {}
elements_cfg = cfg.get("elements") or {}

# paths.handling: "filename" | "describe" | "read"
legacy_path = (text_cfg.get("paths") or {}).get("handling")
if legacy_path and "file_path" not in (cfg.get("markup") or {}):
    if legacy_path in {"skip", "filename", "describe", "read"}:
        base["file_path"] = Treatment(legacy_path)

# elements.code_block: "skip" | "describe" | "read"
legacy_code = elements_cfg.get("code_block")
if legacy_code and "code_fence" not in (cfg.get("markup") or {}):
    if legacy_code in {"skip", "describe", "read"}:
        base["code_fence"] = Treatment(legacy_code)
```

- [ ] **Step 2: Test**

```python
def test_load_treatments_honors_legacy_paths_handling():
    cfg = {"mode": "direct", "text": {"paths": {"handling": "describe"}}}
    out = load_treatments(cfg)
    assert out["file_path"].kind == "describe"
```

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/markup/forms.py core/tests/test_markup_forms.py
git commit -m "feat(markup): legacy text.paths/elements.code_block compat shim (Phase 26 Task 13)"
```

---

## Task 14: Final regression sweep

- [ ] **Step 1: Run the full backend suite**

Run: `pytest core/tests/ -x`
Expected: all green (906+ existing + ~30 new = ~936+ passing).

- [ ] **Step 2: Manual smoke**

Start daemon, run `claude` in a sandbox project, ask it to "show me a python function", verify the narrator says "a code block of …" instead of reading code aloud.

- [ ] **Step 3: Commit anything that fell out of regression fixes**

- [ ] **Step 4: Hand off to Phase 25c**

---

## Notes for the implementer

- Recognizers must be **stateless** and **fast**: compile every regex once at module top.
- The `_audible_passthrough` token (`\x00AUDIBLE{i}\x00`) must never appear in user prose; if it ever does, that's a bug in `audible_block` recognition.
- Pipeline runs many regexes against potentially large prose — keep an eye on test timing. If any test exceeds 100ms, profile.
- DRY: every `apply_treatment` branch should call into `describer.py` — no string-formatting in `treatment.py`.
- YAGNI: don't add a "custom recognizer" hook in v1. Phase 27+ if demand emerges.
- TDD: each task above writes the failing test first; implementation lands only after the test fails as expected.
- Frequent commits: every task ends with a commit. If a task gets long, split mid-task.
