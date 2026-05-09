# CCT Phase 26 — Claude Code Markup Awareness

**Status**: approved 2026-05-09 (autonomous overnight build), awaiting user verification.
**Scope**: structure-aware narration. The narrator recognizes 10 Claude Code markup forms and applies per-form treatment settings. New "Markup" tab in legacy UI exposes per-form controls.
**Reference**: parent roadmap entry in [2026-05-08-cct-v1-design.md](./2026-05-08-cct-v1-design.md).

## Context

After Phase 21's CC-tuned trigger pack, Claude knows when to write `## Audible <Tag>` blocks. But the narrator's *content* awareness is still generic — it treats Claude Code prose as plain markdown. It doesn't know to skip a code fence, summarize a TodoWrite update, or describe a tool-output block. Settings like `mode: brief` only have meaningful effect over a structure-aware narrator.

Phase 26 binds codetalker's settings UI directly to Claude Code's response *structures* by giving each recognized form its own dedicated treatment row. The settings UI becomes a literal map of Claude Code's response vocabulary; adding a new recognizer is mechanically the same as adding a new row.

## Decisions locked in

- **Per-form settings panel**, not a single global verbosity dial.
- **Modes as presets** that pre-populate per-form treatments. Each row individually overridable.
- **Per-trigger-tag overrides** via new `markup_overrides: dict` field on `Tag`.
- **All 10 markup forms in v1**: code_fence, inline_code, todo_update, plan_block, audible_block, system_reminder, tool_output, subagent_dispatch, file_path, long_numeral.
- **Settings UI ships in legacy UI first** as a "Markup" tab; React dashboard gets a link-out until Phase 27 ports it.
- **Existing `text/` filters** (paths.handling, long_numeral) fold into the new framework via a load-time read shim for backward compat.

## Architecture

```
core/claude_code_talker/markup/
├── __init__.py
├── forms.py              # Form catalog + Treatment dataclass + presets
├── recognizers.py        # detect_<form>(text|event) → list[Span]
├── treatment.py          # apply_treatment(span, treatment, cfg) → str | None
├── pipeline.py           # transform(prose, cfg), transform_event(event, cfg)
└── describer.py          # human-language renderers ("a code block of about N lines")

modes/direct.py           # MODIFY — replace _postprocess with markup.pipeline.transform
modes/live.py             # MODIFY — call transform_for_live in _trigger_handler + _emit_chunk
event_render.py           # MODIFY — use describer for tool_output (Bash etc.)
triggers/tags.py          # MODIFY — Tag.markup_overrides field

static/index.html         # MODIFY — add Markup tab button + pane
static/app.js             # MODIFY — TAB_RENDERERS.markup with per-form rows
webui/src/components/SessionControls.tsx  # MODIFY — link-out to /ui/#markup

core/tests/
├── test_markup_recognizers.py     # 12 tests
├── test_markup_treatment.py       # 8 tests
├── test_markup_pipeline.py        # 7 tests
└── test_markup_api.py             # 3 tests
```

No daemon redesign. Pipeline is a swap-in to existing modes; audio queue, SSE, trigger parser unchanged.

## Section 1 — Data model

```python
@dataclass(frozen=True)
class Treatment:
    kind: str       # see FORM_KINDS below
    params: dict = field(default_factory=dict)


FORM_KINDS = {
    "code_fence":         {"skip", "describe", "read"},
    "inline_code":        {"skip", "identifier_only", "read"},
    "todo_update":        {"skip", "count_only", "itemize", "read"},
    "plan_block":         {"skip", "summarize", "read"},
    "audible_block":      {"speak"},                 # locked — trigger mode owns
    "system_reminder":    {"skip", "log_silently"},
    "tool_output":        {"skip", "describe", "read"},
    "subagent_dispatch":  {"skip", "announce", "describe"},
    "file_path":          {"skip", "filename", "describe", "read"},
    "long_numeral":       {"skip", "describe", "read"},
}
```

Stored in cfg as nested dicts under `markup.<form>` with `kind` + `params`. `markup.forms.load_treatments(cfg)` returns `dict[str, Treatment]`, validates kinds, falls back to active mode preset on error.

## Section 2 — Recognizers

| Form | Detection signal | Notes |
|---|---|---|
| `code_fence` | `r"^```[^\n]*\n[\s\S]*?\n```"` multiline | Records `language`, `line_count`. Indented code out of v1. |
| `inline_code` | `r"\`[^\`\n]+\`"` | `parsed["is_identifier"]` via `^[A-Za-z_][\w.]*$` |
| `todo_update` | From `tool_use.name == "TodoWrite"` events | Reuses `event_render.summarize_tool_input` |
| `plan_block` | `r"^## Plan\s*\n"` OR `tool_use.name in {"ExitPlanMode"}` | |
| `audible_block` | Already handled by `triggers/parser.py:parse_blocks` | Recognizer asks parser; never overrides |
| `system_reminder` | `r"<system-reminder>[\s\S]*?</system-reminder>"` + legacy prefix list | Treatment limited to skip/log_silently |
| `tool_output` | From `POST_TOOL` events | `parsed["tool_name"]`, `exit_code`, `line_count` |
| `subagent_dispatch` | `tool_use.name == "Task"` (PRE+POST) | Correlated by `tool_use_id` |
| `file_path` | Existing `transcript._FILE_PATH` regex | Lifted verbatim |
| `long_numeral` | Existing `transcript._LONG_NUMERIC` (`\b\d{7,}\b`) | Configurable treatment |

Subagent and tool-output recognizers run against `Event` objects, not prose text. Pipeline accepts both: `transform(prose, cfg)` for prose; `transform_event(event, cfg)` for tool events.

## Section 3 — Treatment dispatch pipeline

`markup.pipeline.transform(prose, cfg)` is the single entry point for prose. Fixed pipeline order:

1. **Skip-pass (block-level)**: `system_reminder`, `audible_block` (passthrough), `code_fence`, `plan_block`, `tool_output` — removed/replaced wholesale before sub-tokenization.
2. **Span-pass (inline)**: `inline_code`, `file_path`, `long_numeral` — rewrite spans within remaining prose.
3. **Final cleanup**: collapse whitespace runs introduced by deletions.

Audible blocks pass through verbatim — trigger parser still owns TTS dispatch.

## Section 4 — Mode-as-presets table

| Form | brief | direct | live | trigger |
|---|---|---|---|---|
| code_fence | skip | describe | describe | skip |
| inline_code | identifier_only | read | identifier_only | identifier_only |
| todo_update | count_only | itemize(max=5) | itemize(max=3) | skip |
| plan_block | summarize(60w) | read | summarize(80w) | skip |
| audible_block | speak | speak | speak | speak |
| system_reminder | skip | skip | skip | skip |
| tool_output | describe | read | describe | skip |
| subagent_dispatch | announce | describe | describe | skip |
| file_path | filename | filename | filename | filename |
| long_numeral | describe | describe | describe | describe |

`load_treatments(cfg)` overlays user values on top of preset; preset is the floor.

## Section 5 — Settings UI (legacy /ui/)

- `static/index.html`: add `<button class="tab" data-tab="markup">Markup</button>` + matching pane
- `static/app.js`: `TAB_RENDERERS.markup = function(pane, s, cfg) { ... }` iterates form catalog, renders one row per form using `makeFieldSelect` (form name → kind dropdown) + inline params editor when needed
- Each row shows preset-default badge (◆) when current value matches active mode's preset
- Persistence via existing `updateOverlayKeypath(s.session_id, "markup."+form, {kind})` → `/api/sessions/{id}/overlay`

React dashboard's `SessionControls.tsx` gets a one-line "Markup settings" link to `/ui/#markup`.

## Section 6 — Per-tag overrides

`Tag` dataclass gains `markup_overrides: dict = field(default_factory=dict)`. When `live.py:_trigger_handler` finds a matching `## Audible <Tag>` block, it composes a temporary cfg via `deep_merge(cfg, {"markup": tag.markup_overrides})` and runs the block content through `markup.pipeline.transform` with that composed cfg. Effect: `audible_plan_entry` can ship `{"plan_block": {"kind": "read"}}` to override global summarization for plan content.

`from_cfg` already silently drops unknown fields — no migration needed for existing tags.

## Section 7 — Tests (~30 new)

- `test_markup_recognizers.py` (12) — each form's detection signal + false-positive guards
- `test_markup_treatment.py` (8) — each kind × representative span; invalid kind falls back to preset
- `test_markup_pipeline.py` (7) — strip-then-replace ordering, audible passthrough, overlay precedence, per-tag override
- `test_markup_api.py` (3) — GET/PUT `/api/markup/config`, validation
- Update `test_modes_direct.py` — assert legacy `paths.handling=filename` still works after migration shim

## Section 8 — Implementation phases (14 TDD tasks)

1. Forms catalog + Treatment dataclass + validation (`forms.py`)
2. Recognizers: prose-only forms (code_fence, inline_code, system_reminder, file_path, long_numeral, audible_block, plan_block)
3. Recognizers: event-driven forms (todo_update, tool_output, subagent_dispatch)
4. Treatment dispatch + describer
5. Pipeline assembly (transform, transform_for_live, transform_event)
6. Wire into `direct.py` (replace `_postprocess` path/url)
7. Wire into `live.py` (`_trigger_handler` + `_emit_chunk`)
8. Wire into `event_render.py` (Bash output via describer)
9. REST endpoints: `GET/PUT /api/markup/config`
10. Mode preset tables (`preset_for_mode`)
11. Tag schema extension (`Tag.markup_overrides`)
12. Legacy UI Markup tab (HTML + JS renderer)
13. React dashboard link-out
14. Migration shim for `paths.handling` + `elements.code_block`

Tasks 1–5 sequential. 6/7/8 parallelizable. 9 depends on 5. 10/11 independent. 12 depends on 10. 13/14 independent.

## Risks / open questions

- **False positive in audible-block content** containing a code fence. Mitigation: audible-block recognizer runs first, passes content through unchanged; inner forms inside not re-recognized.
- **Performance on long prose**. ~10 regexes × hundreds of KB. Compiled regexes; ~O(10·n). Test: pipeline_perf_under_50ms_for_50kb.
- **Migration of `paths.handling` and `elements.code_block`**. Load-time shim only — never write back to legacy keys. Document deprecation in cfg template comment.
- **`audible_block` row in panel**. Locked to `speak`; UI shows row read-only with tooltip pointing to Triggers tab.

## Out of scope (deferred)

- React-native Markup tab (Phase 27 picks this up)
- Frequency-grouped accordion view (Phase 27)
- Auto-disabling rare recognizers (future phase)
- Custom user-defined recognizers (future phase)

## Verification

1. `pytest core/tests/test_markup*.py` — all new tests pass
2. Full backend regression — 906+ existing tests stay green
3. Manual: enable `code_fence: skip` per-session → trigger a Claude prompt that includes a code fence → narration omits code; mode-preset tooltip shows ◆ on matching rows
