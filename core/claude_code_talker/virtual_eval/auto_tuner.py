"""Propose teacher_mode cfg diffs from aggregated persona feedback."""
from __future__ import annotations

import json
import logging
import re

from claude_code_talker.virtual_eval.aggregator import AggregateReport


# User-locked set of teacher_mode fields the auto-tuner is allowed to propose.
# Anything else returned by the LLM is dropped.
TUNABLE_FIELDS = (
    "depth_level", "verbosity", "granularity",
    "substitution", "glossary", "reframe",
    "prompt_directive_extras",
)

# Field-value validators
_VALID_VERBOSITY = {"concise", "standard", "expanded"}
_VALID_GRANULARITY = {"combined", "per-file"}

# Safety: if the LLM proposes more than this many field changes in one pass,
# mark the tuning as pending_approval rather than auto-applying it.
MAX_FIELDS_PER_PASS = 3

# Cap on prompt_directive_extras to avoid arbitrary large strings landing in cfg.
_EXTRAS_MAX_CHARS = 500


TUNING_PROMPT_TEMPLATE = """\
You are tuning a developer-tool's audio-narration teacher-mode settings based
on virtual-user feedback.

CURRENT teacher_mode CONFIG:
{current_cfg}

VIRTUAL USER EVAL REPORT:
- Total narrations evaluated: {total_evals}
- Cross-persona overall averages: {overall}
- Per-persona breakdown: {per_persona}
- Systemic jargon (terms flagged by 3+ personas with frequency):
{systemic_jargon}
- Missing context samples (what listeners said was unclear):
{missing_context}
- Expectation gaps (where personas got something different than they expected):
{expectation_gaps}

Your job: propose AT MOST {max_fields} field changes to the teacher_mode
config that would address the systemic issues. Do NOT propose changes that
won't measurably help. If everything looks fine, propose ZERO changes.

Allowed field names + value constraints:
- depth_level: integer 1-5 (1=expert audience, 5=full beginner)
- verbosity: "concise" | "standard" | "expanded"
- granularity: "combined" | "per-file"
- substitution / glossary / reframe: boolean
- prompt_directive_extras: string (<=500 chars; appended to teacher prompt to
  address systemic jargon — e.g. "When mentioning 'CTE', briefly note it's a
  temporary database query.")

Return JSON ONLY, no preamble:
{{"fields_to_set": {{...}}, "reasoning": "one short paragraph"}}"""


def parse_tuning_response(raw: str) -> dict:
    """Parse the LLM tuning response. Always returns a dict with fields_to_set
    and reasoning keys; invalid input yields empty fields_to_set."""
    text = (raw or "").strip()
    fence = re.compile(r"^```(?:json)?\s*\n?(.+?)\n?```$", re.DOTALL)
    m = fence.match(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"fields_to_set": {}, "reasoning": ""}
    if not isinstance(data, dict):
        return {"fields_to_set": {}, "reasoning": ""}
    raw_fields = data.get("fields_to_set") or {}
    if not isinstance(raw_fields, dict):
        raw_fields = {}
    cleaned: dict = {}
    for k, v in raw_fields.items():
        if k not in TUNABLE_FIELDS:
            continue
        if k == "depth_level":
            try:
                v = int(v)
                cleaned[k] = max(1, min(5, v))
            except (TypeError, ValueError):
                continue
        elif k == "verbosity":
            if v in _VALID_VERBOSITY:
                cleaned[k] = v
        elif k == "granularity":
            if v in _VALID_GRANULARITY:
                cleaned[k] = v
        elif k in ("substitution", "glossary", "reframe"):
            if isinstance(v, bool):
                cleaned[k] = v
        elif k == "prompt_directive_extras":
            if isinstance(v, str):
                # Strip control chars (incl null bytes), cap length
                stripped = "".join(c for c in v if c.isprintable() or c in "\n\t")
                cleaned[k] = stripped[:_EXTRAS_MAX_CHARS]
    reasoning = str(data.get("reasoning", ""))[:500]
    return {"fields_to_set": cleaned, "reasoning": reasoning}


async def propose_tuning(
    report: AggregateReport,
    current_cfg: dict,
    provider,
    *,
    max_fields: int = MAX_FIELDS_PER_PASS,
) -> dict:
    """Ask the LLM for a tuning proposal grounded in the aggregate report.

    Returns:
        {
            "fields_to_set": {...},  # validated cfg changes
            "reasoning": "...",
            "pending_approval": bool,  # True if proposed changes > max_fields
        }
    """
    expectation_gaps_lines = []
    for gap in report.expectation_gaps[:10]:
        expectation_gaps_lines.append(
            f'- {gap["persona"]} on "{gap["narration_excerpt"]}":\n'
            f'    expected: {gap["expected"]}\n'
            f'    received: {gap["received"]}'
        )
    prompt = TUNING_PROMPT_TEMPLATE.format(
        current_cfg=json.dumps(current_cfg, indent=2)[:1000],
        total_evals=report.total_evals,
        overall=json.dumps(report.overall),
        per_persona=json.dumps(report.per_persona)[:1500],
        systemic_jargon=json.dumps(report.systemic_jargon),
        missing_context="\n".join(f"- {m}" for m in report.missing_context_samples[:10]),
        expectation_gaps="\n".join(expectation_gaps_lines) or "(none)",
        max_fields=max_fields,
    )
    try:
        raw = await provider.complete(prompt, max_tokens=400)
    except Exception as e:
        logging.debug("tuning proposal failed: %s", e)
        return {"fields_to_set": {}, "reasoning": "", "pending_approval": False}
    parsed = parse_tuning_response(raw)
    parsed["pending_approval"] = len(parsed["fields_to_set"]) > max_fields
    return parsed
