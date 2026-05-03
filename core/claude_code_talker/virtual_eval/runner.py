"""Sample selection + batch eval execution for virtual user evaluation."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field

from claude_code_talker.narration_log import NarrationLog


# Modes worth evaluating (excludes test/diagnostic modes that aren't user-facing).
DEFAULT_INCLUDED_MODES = ("live", "live-stream", "brief", "prompt-brief", "chat")


@dataclass
class EvalRequest:
    """Parameters controlling a single virtual-eval run."""
    max_narrations: int = 50
    deployed_at: float = 0.0  # only narrations with timestamp >= this are eligible
    included_modes: tuple[str, ...] = DEFAULT_INCLUDED_MODES
    seed: int | None = None  # for deterministic sampling in tests


def select_narration_sample(log: NarrationLog, request: EvalRequest) -> list[dict]:
    """Read all narration entries; filter by mode + deployed_at; stratified-cap.

    Returns a list of plain dicts (the same shape `NarrationLog.tail()` returns).
    Stratified sampling means each included mode contributes proportional entries
    when the eligible set exceeds ``max_narrations`` — preserves mode diversity.
    """
    # Read everything (NarrationLog.tail with a huge limit captures all)
    all_entries = log.tail(n=10_000)
    eligible = [
        e for e in all_entries
        if e.get("mode") in request.included_modes
        and float(e.get("timestamp", 0)) >= request.deployed_at
    ]
    if not eligible:
        return []
    if len(eligible) <= request.max_narrations:
        return eligible
    # Stratified sample: split by mode, sample proportional to mode-share
    by_mode: dict[str, list[dict]] = {}
    for e in eligible:
        by_mode.setdefault(e["mode"], []).append(e)
    rng = random.Random(request.seed)
    per_mode = max(1, request.max_narrations // len(by_mode))
    sampled: list[dict] = []
    for mode, entries in by_mode.items():
        if len(entries) <= per_mode:
            sampled.extend(entries)
        else:
            sampled.extend(rng.sample(entries, per_mode))
    # If we under-shot the cap (small modes), top up with random eligible
    if len(sampled) < request.max_narrations:
        remaining = [e for e in eligible if e not in sampled]
        deficit = request.max_narrations - len(sampled)
        if remaining and deficit > 0:
            sampled.extend(rng.sample(remaining, min(deficit, len(remaining))))
    return sampled[:request.max_narrations]


# ---------------------------------------------------------------------------
# Task 3: PersonaScore + LLM scoring machinery
# ---------------------------------------------------------------------------

from claude_code_talker.virtual_eval.personas import Persona  # noqa: E402


SCORE_PROMPT_TEMPLATE = """\
You are {name}, {role}. Your primary lens for consuming this content: {primary_lens}.
Your jargon comfort: {comfort_with_jargon}/5 (1=jargon-allergic, 5=fluent).
What you most care about hearing: {what_they_care_about}.

SESSION CONTEXT (so you can judge the narration in context, not in isolation):

User's most recent prompt in this session:
  "{last_user_prompt}"

Recent transcript turns (most recent last):
{transcript_lines}

Prior narrations you would have already heard from this session:
{prior_narrations}

NARRATION TO SCORE (the latest one):

  "{narration}"

THIS IS A TWO-STEP EXERCISE:

Step 1 — Before judging the narration, write down (in your own voice, one short
sentence) WHAT YOU EXPECTED to hear given the session context above. What were
you hoping codetalker would tell you here?

Step 2 — Now compare that expectation to what was actually said. Score on a
1-5 scale (integers only):
  - clarity: how easily YOU (with your background) understood THIS narration
  - helpfulness: did it tell you something useful given what was already happening
  - jargon_load: 1=plain English, 5=dense jargon
  - expectation_match: how close was the narration to what you expected (1=miles off, 5=spot on)

Then briefly answer:
  - expected: what you were hoping to hear (one sentence — your Step 1 answer)
  - received: what you actually got, in your own words (one short sentence)
  - confusing_terms: list any terms that needed defining (array of strings, may be empty)
  - missing_context: what would have made this more useful (one short sentence; "" if nothing)

Respond as JSON ONLY, no preamble. Schema:
{{"clarity": <1-5>, "helpfulness": <1-5>, "jargon_load": <1-5>, "expectation_match": <1-5>,
  "expected": "...", "received": "...",
  "confusing_terms": [...], "missing_context": "..."}}"""


@dataclass
class PersonaScore:
    persona_name: str
    narration_text: str
    clarity: int
    helpfulness: int
    jargon_load: int
    # Expectation gap — measures the distance between what the persona was
    # HOPING to hear (given session context) and what they actually heard.
    # Surfaces "flying blind" gaps that pure clarity scores miss.
    expectation_match: int = 3
    expected: str = ""    # one-sentence description of what the persona expected
    received: str = ""    # one-sentence description of what they actually got
    confusing_terms: list[str] = field(default_factory=list)
    missing_context: str = ""


def build_score_prompt(persona: Persona, narration) -> str:
    """Render the score-request prompt for one (persona, narration) pair.

    Accepts EITHER a plain narration string (back-compat) OR a
    NarrationWithContext for full session-aware scoring (preferred path).
    """
    from claude_code_talker.virtual_eval.context import NarrationWithContext
    if isinstance(narration, NarrationWithContext):
        narration_text = narration.text[:1500]
        last_user_prompt = (narration.last_user_prompt or "(no prior user prompt found)")[:600]
        transcript_lines = (
            "\n".join(narration.recent_transcript_lines) or "(no transcript context available)"
        )
        prior_narrations = (
            "\n".join(f"- {p}" for p in narration.prior_narrations)
            or "(no prior narrations in this session)"
        )
    else:
        # Back-compat: plain string narration with no context.
        narration_text = str(narration)[:1500]
        last_user_prompt = "(context unavailable)"
        transcript_lines = "(context unavailable)"
        prior_narrations = "(context unavailable)"
    return SCORE_PROMPT_TEMPLATE.format(
        name=persona.name,
        role=persona.role,
        primary_lens=persona.primary_lens,
        comfort_with_jargon=persona.comfort_with_jargon,
        what_they_care_about=persona.what_they_care_about,
        last_user_prompt=last_user_prompt,
        transcript_lines=transcript_lines,
        prior_narrations=prior_narrations,
        narration=narration_text,
    )


def _clamp(n, lo: int = 1, hi: int = 5) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        return 3
    return max(lo, min(hi, v))


def parse_score_response(persona_name: str, narration_text: str, raw: str) -> PersonaScore:
    """Parse the LLM's JSON score response into a PersonaScore.

    Tolerates markdown fences. Clamps out-of-range integers. Falls back to
    neutral 3s if the response isn't parseable rather than failing the batch.
    """
    text = (raw or "").strip()
    fence = re.compile(r"^```(?:json)?\s*\n?(.+?)\n?```$", re.DOTALL)
    m = fence.match(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return PersonaScore(
            persona_name=persona_name, narration_text=narration_text,
            clarity=3, helpfulness=3, jargon_load=3,
            confusing_terms=[], missing_context="",
        )
    if not isinstance(data, dict):
        data = {}
    confusing = data.get("confusing_terms") or []
    if not isinstance(confusing, list):
        confusing = []
    confusing = [str(t).strip() for t in confusing if str(t).strip()]
    missing = data.get("missing_context") or ""
    if not isinstance(missing, str):
        missing = str(missing)
    expected = str(data.get("expected", ""))[:300]
    received = str(data.get("received", ""))[:300]
    return PersonaScore(
        persona_name=persona_name,
        narration_text=narration_text,
        clarity=_clamp(data.get("clarity", 3)),
        helpfulness=_clamp(data.get("helpfulness", 3)),
        jargon_load=_clamp(data.get("jargon_load", 3)),
        expectation_match=_clamp(data.get("expectation_match", 3)),
        expected=expected,
        received=received,
        confusing_terms=confusing[:10],  # cap to keep aggregator tractable
        missing_context=missing[:300],
    )


async def run_eval_batch(
    personas: list[Persona],
    sample,  # list[dict] OR list[NarrationWithContext]
    provider,
    *,
    batch_size: int = 10,
    max_tokens: int = 250,
) -> list[PersonaScore]:
    """Score every (persona × narration) pair using full session context.

    ``sample`` may be a list of plain narration-log dicts OR a list of
    NarrationWithContext objects. The latter is the preferred input —
    NarrationWithContext carries prior narrations + last user prompt + recent
    transcript so personas can score in context, not in isolation.

    Runs LLM calls in concurrent batches of ``batch_size`` to keep latency low.
    Provider failures degrade gracefully to neutral scores; the eval never
    raises end-to-end.
    """
    from claude_code_talker.virtual_eval.context import NarrationWithContext
    pairs = [(p, n) for p in personas for n in sample]
    results: list[PersonaScore] = []

    async def _one_call(persona: Persona, narration) -> PersonaScore:
        if isinstance(narration, NarrationWithContext):
            text = narration.text
        elif isinstance(narration, dict):
            text = narration.get("text", "")
        else:
            text = str(narration)
        try:
            raw = await provider.complete(build_score_prompt(persona, narration), max_tokens=max_tokens)
        except Exception as e:
            logging.debug("virtual eval call failed: %s", e)
            return PersonaScore(
                persona_name=persona.name, narration_text=text,
                clarity=3, helpfulness=3, jargon_load=3,
            )
        return parse_score_response(persona.name, text, raw)

    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i:i + batch_size]
        chunk_results = await asyncio.gather(*[_one_call(p, n) for p, n in chunk])
        results.extend(chunk_results)
    return results
