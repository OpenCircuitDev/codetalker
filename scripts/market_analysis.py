#!/usr/bin/env python3
"""Market analysis — virtual 50-user product evaluation for CodeTalker.

Builds on the existing virtual_eval scaffolding (which scores teacher-mode
narrations against 5 personas for auto-tuning) but scales to 50 personas
across 7 product dimensions plus open-ended feedback. The output is a
human-readable markdown report + a JSON raw-data file.

Methodology in three phases:

  1. Sample real narrations from ~/.claude/scripts/codetalker/narration-log.jsonl
     so personas see what users actually hear, not synthetic examples.
  2. Generate 50 diverse vibe-developer personas in 10 parallel batches of 5
     (each batch with a different axis emphasis — beginners / power users /
     non-CS founders / multitasking ops / etc).
  3. Each persona scores the product on 7 dimensions and answers 4 open-
     ended questions. Scores aggregate; free text gets thematic clustering.

Run from the codetalker repo root:

    python scripts/market_analysis.py

Output:
    MARKET_ANALYSIS_<DATE>.md   human-readable report
    MARKET_ANALYSIS_<DATE>.json raw scores + per-persona free text

Cost: ~$0.20 on Haiku 4.5 via OpenRouter. Runtime: ~3-5 minutes.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import random
import re
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import httpx
import yaml


# ─── Config ──────────────────────────────────────────────────────────────────


REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = Path.home() / ".claude" / "scripts" / "codetalker" / "secrets.yaml"
NARRATION_LOG = Path.home() / ".claude" / "scripts" / "codetalker" / "narration-log.jsonl"

MODEL = "anthropic/claude-haiku-4.5"
TIMEOUT_SECONDS = 60.0
PERSONA_BATCH_COUNT = 10        # 10 batches × 5 personas = 50 total
PERSONAS_PER_BATCH = 5
CONCURRENCY = 5                 # max in-flight OpenRouter requests
NARRATION_SAMPLE_SIZE = 10      # how many real narrations each persona sees

DIMENSIONS = [
    "clarity",                # the narration is easy to follow without re-listening
    "decision_helpfulness",   # it actually helps you decide what to do next
    "cadence",                # the right amount of audio — not too much / too little
    "freshness",              # info is timely, not stale by the time you hear it
    "relatability",           # feels like a useful colleague, not a robot reading logs
    "ui_usability",           # the webui is intuitive and findable
    "feature_completeness",   # the product covers what a user in your shoes would need
]

logging.basicConfig(format="%(asctime)s %(message)s", datefmt="%H:%M:%S", level=logging.INFO)
log = logging.getLogger("market_analysis")


# ─── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class Persona:
    name: str
    role: str
    vibe_experience: str          # one of: fresh, mid, veteran, power
    domain_expertise: str         # one of: novice, mid, senior, expert
    primary_use_case: str
    listening_context: str        # where/when they listen
    what_they_care_about: str


@dataclass
class PersonaEval:
    persona: Persona
    scores: dict[str, int] = field(default_factory=dict)
    surprises: str = ""
    would_remove: str = ""
    would_add: str = ""
    recommendation: str = ""
    nps: int = 0
    subscribe_pro: bool = False
    raw_response: str = ""
    # Iteration 3 (2026-05-21) — open-ended fields gated on --efficiency-questions.
    # Default empty so iteration 1 + 2 reports don't change shape.
    efficiency_gap: str = ""        # what would let you work faster?
    understanding_gap: str = ""     # what about your session do you wish you
                                    # understood better that we're not surfacing?


# ─── OpenRouter client ───────────────────────────────────────────────────────


def load_api_key() -> str:
    secrets = yaml.safe_load(SECRETS_PATH.read_text(encoding="utf-8"))
    key = (secrets.get("openrouter_api_key") or "").strip()
    if not key:
        sys.exit(f"openrouter_api_key not set in {SECRETS_PATH}")
    return key


async def complete(client: httpx.AsyncClient, api_key: str, prompt: str,
                   *, system: Optional[str] = None, max_tokens: int = 2000,
                   temperature: float = 0.9) -> str:
    """Call OpenRouter's chat completions endpoint and return the text."""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = {
        "model": MODEL, "messages": msgs,
        "max_tokens": max_tokens, "temperature": temperature,
    }
    r = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body, timeout=TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


def extract_json(text: str) -> Optional[dict | list]:
    """Find and parse a JSON object/array embedded in an LLM response.

    Handles three common cases:
      1. Bare JSON (the whole response IS JSON)
      2. JSON in ```json fenced block
      3. JSON with trailing prose
    """
    # Fenced block first — most common with Anthropic models.
    m = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find the first { or [ and the matching closer.
    for opener, closer in [("[", "]"), ("{", "}")]:
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


# ─── Sampling narrations ─────────────────────────────────────────────────────


def sample_narrations(n: int, since_ts: float = 0.0) -> list[dict]:
    """Pull a diverse sample of recent narrations from the log.

    Diverse = at least one per (mode × voice) combination we see, with the
    rest filled in from the most-recent entries. Filters out tagged error
    captions ("[stt error: ...]") so personas don't evaluate broken cases.
    """
    if not NARRATION_LOG.exists():
        return []
    entries = []
    for line in NARRATION_LOG.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = (e.get("text") or "").strip()
        if not text or text.startswith("[") or len(text) < 30:
            continue
        # 2026-05-21 — iteration 2: optional timestamp filter so we sample
        # only narrations produced AFTER a given commit (e.g. the briefness
        # pass). Without this, iteration 2 would score the same content as
        # iteration 1 and produce a meaningless "no change" delta.
        if since_ts > 0 and float(e.get("timestamp", 0)) < since_ts:
            continue
        # 2026-05-21 — only keep modes that the prompts actually drive
        # (live-stream, brief, prompt-brief). Skip "trigger" entries which
        # are user prompt summaries reproduced verbatim and aren't a
        # product of the live/brief system prompts.
        mode = (e.get("mode") or "").lower()
        if since_ts > 0 and mode not in ("live-stream", "brief", "live", "direct"):
            continue
        entries.append(e)
    if not entries:
        return []
    # Take the most recent 1000, then shuffle and pick n.
    recent = entries[-1000:]
    random.shuffle(recent)
    # Force at least one of each (mode, voice) pair we encounter.
    seen_combos: set[tuple[str, str]] = set()
    sample = []
    for e in recent:
        combo = (e.get("mode", ""), e.get("voice", ""))
        if combo not in seen_combos:
            sample.append(e)
            seen_combos.add(combo)
            if len(sample) >= n:
                break
    while len(sample) < n and len(recent) > len(sample):
        e = recent[len(sample)]
        if e not in sample:
            sample.append(e)
    return sample[:n]


# ─── Persona generation ──────────────────────────────────────────────────────


BATCH_FOCUSES = [
    "complete beginners — first month using Claude Code, first language",
    "ex-frontend devs learning a new backend stack",
    "senior engineers (10+ yrs) trying AI tooling for the first time",
    "indie SaaS founders running 3+ parallel agent sessions",
    "non-CS researchers / academics using AI to build their first tool",
    "DevOps engineers running long agentic infrastructure tasks",
    "game devs (Unity / Unreal) with C++/C# background",
    "data scientists running long ML pipelines with AI assistance",
    "designers-who-code building landing pages and prototypes",
    "power users running 5+ agent sessions with custom voice setups",
]


def persona_generation_prompt(focus: str) -> str:
    return f"""\
Generate exactly 5 diverse VIBE DEVELOPER personas focused on this archetype:

  {focus}

Vibe developers' primary workflow is chatting with an AI assistant (Claude
Code, Cursor, Windsurf), lightly steering, often not watching the code as
it's written. CodeTalker narrates what the AI is doing OUT LOUD so they
can step away or multitask.

Each persona is a JSON object with:
  name              — first name only
  role              — their job title or self-description
  vibe_experience   — one of: "fresh", "mid", "veteran", "power"
  domain_expertise  — one of: "novice", "mid", "senior", "expert"
  primary_use_case  — what they're building right now (1 sentence)
  listening_context — where + when they listen to CodeTalker
                     (e.g. "on a commute", "while cooking dinner",
                      "running parallel sessions in the same room")
  what_they_care_about — one sentence on what matters most about the
                         narration for THEM specifically

Vary the names so the 5 personas feel distinct. Make them realistic, not
caricatures. Some should have unflattering things to say (impatient with
verbosity, distrustful of AI, etc.). Avoid making everyone enthusiastic.

Return ONLY a JSON array of 5 objects, no prose around it."""


async def gen_persona_batch(client: httpx.AsyncClient, api_key: str,
                            focus: str) -> list[Persona]:
    raw = await complete(client, api_key, persona_generation_prompt(focus),
                          max_tokens=2000, temperature=1.0)
    parsed = extract_json(raw)
    if not isinstance(parsed, list):
        log.warning("batch '%s' returned non-list, skipping", focus[:40])
        return []
    out = []
    for p in parsed:
        if not isinstance(p, dict):
            continue
        try:
            out.append(Persona(
                name=str(p.get("name", "Anonymous"))[:60],
                role=str(p.get("role", ""))[:120],
                vibe_experience=str(p.get("vibe_experience", "mid"))[:20],
                domain_expertise=str(p.get("domain_expertise", "mid"))[:20],
                primary_use_case=str(p.get("primary_use_case", ""))[:200],
                listening_context=str(p.get("listening_context", ""))[:200],
                what_they_care_about=str(p.get("what_they_care_about", ""))[:300],
            ))
        except Exception as e:
            log.warning("persona parse failed: %s", e)
    return out


# ─── Product context for the eval prompt ─────────────────────────────────────


PRODUCT_DESCRIPTION = """\
CodeTalker is a TTS narrator daemon for AI coding tools (Claude Code,
Cursor, Cline, Continue.dev, and ~10 more via MCP). While the AI works,
CodeTalker speaks out loud — file edits, command runs, decisions, summaries
— so you can step away, listen on a commute, or run multiple sessions in
parallel without watching them.

NARRATION MODES (per-session, switchable in webui or phone):
  - brief         — one-sentence wrap-up at the end of each AI turn (default).
  - live          — streaming sentence-by-sentence as the AI works.
  - direct        — raw tool outputs near-verbatim (deepest detail).
  - critical_only — silent unless something breaks, blocks, or needs your input.

DECISION & CONFIDENCE CUES (audible, prepended before TTS):
  - "Heads up." → an [ALERT] from the narrator: error, blocker, or
                  "drop everything" moment (build broke, migration stuck).
  - "Checkpoint." → a [CHECKPOINT] from the narrator: architecturally-
                    significant decision (schema, API shape, dependency,
                    migration approach) — not routine edits.
  - silent "low confidence" badge → a [UNSURE] from the narrator: hedging
                    an inference rather than reporting a direct observation.
  - "Still here." → heartbeat when the daemon's alive but nothing's worth
                    speaking aloud, so you know it's not crashed.

DECISION RATIONALE — every decision narration must fold a short WHY-clause
("instead of X" / "to avoid Y") into the same sentence, so listeners know
not just WHAT was chosen but why it beat the alternative.

DIFF CLAUSE — when narrating a behavior-changing code edit (not just
rename/format), the narrator folds a short "was X; now Y" clause into
the same sentence ("Tightened the retry loop — was unbounded; now capped
at 3."). The before-state is read from prose + tool actions; the
narrator skips the clause rather than fabricating it. Cosmetic edits
get no diff clause — only behavior changes do.

It has two tiers:
  BASIC (free)     — desktop browser narration via webui. All four modes.
                     Per-session voices via Piper local TTS. OpenRouter /
                     OpenAI / Anthropic LLM for narration. Workspace
                     grouping + session pinning. Rewind-30s + skip pills.
  PRO ($10/mo)     — Android companion app (phone speaker routing).
                     Local voice cloning (XTTS, your own 10s sample).
                     Animated character avatars (XREAL glasses ready).
                     Buddy mode (talk to your agent through the phone).
                     Direct-STT (voice-to-Claude dictation).
                     Multi-session fan-in to a single phone.
"""

UI_DESCRIPTION = """\
The webui has four main tabs:

  SESSIONS    — Live sessions grouped by workspace (e.g. CLIENTS, OCRACING).
                Each row shows: session name, current mode buttons (brief/live),
                pin button, sink chips (Desktop/Phone/Glasses), mute toggle.
                Right panel: real-time narration log scrolling as it speaks.
  ACTIVITY    — Global feed of every line spoken, across every session,
                with timestamps. Filters: speak / tool / subagent / error.
  CHARACTERS  — Library of personas with cloned voices + 3D avatars (Pro).
                Each character has: name, voice slug, persona tone tag.
  PREFERENCES — Audio routing defaults, AR companion pairing (QR token).

Top bar: "codetalker" + green health dot + master "Narration ON/OFF" toggle
+ live-session count badge.
"""

CADENCE_DESCRIPTION = """\
Narration modes (per-session, switchable from webui or phone):
  - Live: streams sentence-by-sentence as the AI works (LLM-driven, 8-12s).
  - Brief: one-sentence wrap-up at the end of each Claude turn, plus a
    mid-turn brief if quiet for 2+ minutes, plus an escalating heartbeat
    if the daemon is alive but nothing's worth speaking:
      1st heartbeat (30s): "Still here."
      2nd heartbeat (60s): "Still here. Quiet two minutes."
      3rd+ (180s+):        "Still on it — N minutes." (capped at 10+)
    The escalation resets when a real brief fires.
  - Direct: raw tool outputs spoken near-verbatim (deepest detail, most noise).
  - Critical_only: stays silent unless an error, blocker, or "needs your
    input" moment fires — uses a 20-word cap, no chatter.

Within any mode, the narrator can prepend the audible cues "Heads up."
(an [ALERT] — error/blocker) or "Checkpoint." (an architectural decision
that warrants attention), and decisions always include a short WHY-clause
in the same sentence ("instead of X", "to avoid Y"). Low-confidence
inferences are silently flagged in the UI badge rather than spoken.

Catch-up tools for when you've been away:
  - Rewind: replay the last 30 seconds of audio for the active session.
  - Skip: drop the current narration if it's already stale to you.
  - Replay decisions: replay only [CHECKPOINT] narrations from the last
    N minutes (default 30) as a highlight reel of architectural choices.
  - Decisions-only filter in the webui Activity tab — hide every
    non-architectural event when you only care about what got committed to.

Each session can independently be muted, paused, or have its mode swapped.
"""


def eval_prompt(persona: Persona, narrations: list[dict], include_efficiency_questions: bool = False) -> str:
    sample_lines = "\n".join(
        f"  [{e.get('mode','?'):>14}] {e.get('voice','?'):<30} \"{e.get('text','').strip()}\""
        for e in narrations
    )
    return f"""\
You are reviewing CodeTalker (a TTS narrator daemon for AI coding tools)
in character. Stay in this persona for the whole response:

  Name:              {persona.name}
  Role:              {persona.role}
  Vibe experience:   {persona.vibe_experience}
  Domain expertise:  {persona.domain_expertise}
  Use case:          {persona.primary_use_case}
  Listening context: {persona.listening_context}
  What they care:    {persona.what_they_care_about}

══════════════════════════════════════════════════════════════════════
THE PRODUCT
{PRODUCT_DESCRIPTION}

══════════════════════════════════════════════════════════════════════
THE WEBUI
{UI_DESCRIPTION}

══════════════════════════════════════════════════════════════════════
CADENCE
{CADENCE_DESCRIPTION}

══════════════════════════════════════════════════════════════════════
WHAT YOU'D ACTUALLY HEAR (10 real samples from a running daemon)

{sample_lines}

══════════════════════════════════════════════════════════════════════
YOUR EVALUATION

Return a single JSON object with EXACTLY these keys (no extra text):

{{
  "scores": {{
    "clarity": <1-5 int>,                    // easy to follow without re-listening
    "decision_helpfulness": <1-5 int>,       // helps you decide what to do next
    "cadence": <1-5 int>,                    // amount of audio — too much/little/right
    "freshness": <1-5 int>,                  // info is timely, not stale
    "relatability": <1-5 int>,               // feels like a colleague, not a robot
    "ui_usability": <1-5 int>,               // webui is intuitive + findable
    "feature_completeness": <1-5 int>        // covers what someone in your shoes needs
  }},
  "surprises": "<1-2 sentences in your voice — what surprised you, good or bad>",
  "would_remove": "<1 sentence — one feature you'd remove or one thing you'd cut>",
  "would_add": "<1 sentence — one feature you'd add>",
  "recommendation": "<1-2 sentences — would you recommend this to someone in your shoes? why or why not?>",
  "nps": <0-10 int>,
  "subscribe_pro": <true or false>{",  // ITERATION 3 ADDITIONS BELOW" if include_efficiency_questions else ""}
{'''  "efficiency_gap": "<1-2 sentences — what SPECIFICALLY would let you work faster or more efficiently with this tool? Name a concrete change to the audio, the UI, the workflow, or the feature set. Be specific to your role.>",
  "understanding_gap": "<1-2 sentences — what about your session (or your sessions if you run multiple) do you wish you understood better that this tool isn't currently surfacing? What's the question you keep wanting to ask the tool that it can't answer right now?>"''' if include_efficiency_questions else ""}
}}

Be specific and in YOUR voice — don't generalize. If you'd say it
bluntly to a friend, say it bluntly here. Score in YOUR shoes —
a power user shouldn't rate clarity high if they want raw facts and
the narration is too chatty for them."""


async def eval_persona(client: httpx.AsyncClient, api_key: str,
                       persona: Persona, narrations: list[dict],
                       include_efficiency_questions: bool = False) -> Optional[PersonaEval]:
    try:
        raw = await complete(
            client, api_key,
            eval_prompt(persona, narrations, include_efficiency_questions),
            max_tokens=2000 if include_efficiency_questions else 1500,
            temperature=0.7,
        )
    except Exception as e:
        log.warning("eval failed for %s: %s", persona.name, e)
        return None
    parsed = extract_json(raw)
    if not isinstance(parsed, dict):
        log.warning("eval for %s returned non-dict, skipping", persona.name)
        return None
    scores = parsed.get("scores") or {}
    if not isinstance(scores, dict):
        scores = {}
    clean_scores = {}
    for dim in DIMENSIONS:
        v = scores.get(dim)
        try:
            iv = int(v) if v is not None else 0
        except (TypeError, ValueError):
            iv = 0
        clean_scores[dim] = max(1, min(5, iv)) if iv else 0
    try:
        nps = int(parsed.get("nps", 0))
    except (TypeError, ValueError):
        nps = 0
    return PersonaEval(
        persona=persona,
        scores=clean_scores,
        surprises=str(parsed.get("surprises", ""))[:500],
        would_remove=str(parsed.get("would_remove", ""))[:300],
        would_add=str(parsed.get("would_add", ""))[:300],
        recommendation=str(parsed.get("recommendation", ""))[:500],
        nps=max(0, min(10, nps)),
        subscribe_pro=bool(parsed.get("subscribe_pro", False)),
        raw_response=raw[:4000],
        # Iteration 3 fields — empty when the flag is off.
        efficiency_gap=str(parsed.get("efficiency_gap", ""))[:500],
        understanding_gap=str(parsed.get("understanding_gap", ""))[:500],
    )


# ─── Concurrency helper ──────────────────────────────────────────────────────


async def bounded_gather(coros, concurrency: int):
    sem = asyncio.Semaphore(concurrency)

    async def runner(coro):
        async with sem:
            return await coro
    return await asyncio.gather(*(runner(c) for c in coros))


# ─── Aggregation + report ───────────────────────────────────────────────────


def aggregate(evals: list[PersonaEval]) -> dict:
    """Per-dimension stats + cohort breakdown + NPS."""
    out = {
        "n": len(evals),
        "dimensions": {},
        "by_vibe_experience": {},
        "nps": {},
        "would_subscribe_pro": 0,
    }
    for dim in DIMENSIONS:
        vals = [e.scores.get(dim, 0) for e in evals if e.scores.get(dim, 0) > 0]
        if not vals:
            out["dimensions"][dim] = {"mean": 0, "median": 0, "stdev": 0, "min": 0, "max": 0, "n": 0}
            continue
        out["dimensions"][dim] = {
            "mean": round(statistics.mean(vals), 2),
            "median": statistics.median(vals),
            "stdev": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0,
            "min": min(vals), "max": max(vals), "n": len(vals),
        }
    # Cohort breakdown — which vibe-experience tier is grumpiest.
    for tier in {"fresh", "mid", "veteran", "power"}:
        tier_evals = [e for e in evals if e.persona.vibe_experience == tier]
        if not tier_evals:
            continue
        cohort = {}
        for dim in DIMENSIONS:
            vals = [e.scores.get(dim, 0) for e in tier_evals if e.scores.get(dim, 0) > 0]
            cohort[dim] = round(statistics.mean(vals), 2) if vals else 0
        out["by_vibe_experience"][tier] = {"n": len(tier_evals), "means": cohort}
    # NPS — % promoters (9-10) minus % detractors (0-6).
    promoters = sum(1 for e in evals if e.nps >= 9)
    passives = sum(1 for e in evals if 7 <= e.nps <= 8)
    detractors = sum(1 for e in evals if e.nps <= 6)
    total = len(evals) or 1
    out["nps"] = {
        "promoters": promoters, "passives": passives, "detractors": detractors,
        "score": round((promoters - detractors) * 100 / total, 1),
        "mean": round(statistics.mean([e.nps for e in evals]), 2) if evals else 0,
    }
    out["would_subscribe_pro"] = sum(1 for e in evals if e.subscribe_pro)
    return out


def _top_phrases(texts: list[str], k: int = 8) -> list[tuple[str, int]]:
    """Cheap n-gram counter to surface recurring themes."""
    bigrams = Counter()
    for t in texts:
        words = re.findall(r"[a-z]+", t.lower())
        for i in range(len(words) - 1):
            bg = f"{words[i]} {words[i+1]}"
            if len(bg) > 8 and not any(stop in bg for stop in (
                "the the", "and the", "to the", "of the", "is a", "in a", "it is",
                "would be", "i would", "would like", "i think",
            )):
                bigrams[bg] += 1
    return bigrams.most_common(k)


def render_report(evals: list[PersonaEval], agg: dict) -> str:
    today = dt.date.today().isoformat()
    lines = []
    lines.append(f"# Market Analysis — CodeTalker")
    lines.append(f"_Generated {today}_ · _{len(evals)} virtual users_ · _Model: {MODEL}_")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(f"50 vibe-developer personas generated in 10 batches of 5 (each batch focused on a different archetype — beginners, power users, non-CS founders, etc.). Each persona was shown the product description, webui description, cadence behavior, and {NARRATION_SAMPLE_SIZE} real narrations sampled from `~/.claude/scripts/codetalker/narration-log.jsonl`. They scored 7 dimensions on a 1-5 scale and answered 4 open-ended questions, in character.")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    nps = agg.get("nps", {})
    pro_n = agg.get("would_subscribe_pro", 0)
    n_total = agg.get("n", 0) or 1
    means = {d: agg["dimensions"][d]["mean"] for d in DIMENSIONS}
    sorted_dims = sorted(means.items(), key=lambda kv: kv[1])
    weakest = sorted_dims[0]
    strongest = sorted_dims[-1]
    lines.append(
        f"- **NPS score: {nps.get('score', 0)}** "
        f"({nps.get('promoters', 0)} promoters · {nps.get('passives', 0)} passives · {nps.get('detractors', 0)} detractors)"
    )
    lines.append(f"- **Would subscribe to Pro: {pro_n}/{n_total} ({round(pro_n * 100 / n_total)}%)**")
    lines.append(f"- **Strongest dimension**: {strongest[0]} (mean {strongest[1]}/5)")
    lines.append(f"- **Weakest dimension**: {weakest[0]} (mean {weakest[1]}/5)")
    lines.append("")
    lines.append("## Dimension scores")
    lines.append("")
    lines.append("| Dimension | Mean | Median | Stdev | Min-Max | n |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for dim in DIMENSIONS:
        s = agg["dimensions"][dim]
        lines.append(
            f"| {dim} | {s['mean']} | {s['median']} | {s['stdev']} | "
            f"{s['min']}-{s['max']} | {s['n']} |"
        )
    lines.append("")
    lines.append("## Cohort breakdown (mean by vibe-experience tier)")
    lines.append("")
    cohorts = agg.get("by_vibe_experience", {})
    if cohorts:
        header = "| Tier (n) | " + " | ".join(DIMENSIONS) + " |"
        sep = "|---|" + "|".join("---:" for _ in DIMENSIONS) + "|"
        lines.append(header)
        lines.append(sep)
        for tier in ("fresh", "mid", "veteran", "power"):
            c = cohorts.get(tier)
            if not c:
                continue
            row = f"| {tier} ({c['n']}) | " + " | ".join(
                str(c["means"].get(d, 0)) for d in DIMENSIONS
            ) + " |"
            lines.append(row)
    lines.append("")
    lines.append("## Recurring themes")
    lines.append("")
    lines.append("### Top bigrams in 'what surprised you'")
    for phrase, n in _top_phrases([e.surprises for e in evals]):
        lines.append(f"- *{phrase}* — {n} mentions")
    lines.append("")
    lines.append("### Top bigrams in 'one feature you'd remove'")
    for phrase, n in _top_phrases([e.would_remove for e in evals]):
        lines.append(f"- *{phrase}* — {n} mentions")
    lines.append("")
    lines.append("### Top bigrams in 'one feature you'd add'")
    for phrase, n in _top_phrases([e.would_add for e in evals]):
        lines.append(f"- *{phrase}* — {n} mentions")
    lines.append("")
    lines.append("## Voice highlights — extreme reactions")
    lines.append("")
    by_nps = sorted(evals, key=lambda e: e.nps)
    detractors = [e for e in by_nps if e.nps <= 6][:5]
    promoters = [e for e in by_nps if e.nps >= 9][:5]
    lines.append("### Loudest detractors")
    for e in detractors:
        lines.append("")
        lines.append(f"**{e.persona.name}** · {e.persona.role} · {e.persona.vibe_experience}/{e.persona.domain_expertise} · NPS {e.nps}")
        lines.append(f"> {e.recommendation}")
        lines.append(f"> Would remove: {e.would_remove}")
        lines.append(f"> Would add: {e.would_add}")
    lines.append("")
    lines.append("### Loudest promoters")
    for e in promoters:
        lines.append("")
        lines.append(f"**{e.persona.name}** · {e.persona.role} · {e.persona.vibe_experience}/{e.persona.domain_expertise} · NPS {e.nps}")
        lines.append(f"> {e.recommendation}")
        lines.append(f"> Would add: {e.would_add}")
    lines.append("")
    lines.append("## All-personas raw scores")
    lines.append("")
    lines.append("| Persona | Vibe/Domain | Clarity | DecHelp | Cadence | Fresh | Relate | UI | Feature | NPS | Pro? |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for e in evals:
        cells = [
            e.persona.name[:24],
            f"{e.persona.vibe_experience}/{e.persona.domain_expertise}",
            *(str(e.scores.get(d, 0)) for d in DIMENSIONS),
            str(e.nps),
            "✓" if e.subscribe_pro else "—",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────


def render_delta(current_agg: dict, baseline_agg: dict) -> str:
    """Render a delta-vs-baseline section comparing two aggregate reports.

    Used by iteration 2+ to show whether dimension scores actually moved
    after an intervention. Positive deltas = improved; negative = worse.
    """
    lines = ["## Delta vs baseline", ""]
    lines.append("| Dimension | Baseline | Current | Δ |")
    lines.append("|---|---:|---:|---:|")
    for dim in DIMENSIONS:
        b = baseline_agg.get("dimensions", {}).get(dim, {}).get("mean", 0)
        c = current_agg.get("dimensions", {}).get(dim, {}).get("mean", 0)
        d = round(c - b, 2)
        arrow = "↑" if d > 0.1 else "↓" if d < -0.1 else "—"
        lines.append(f"| {dim} | {b} | {c} | {arrow} {d:+0.2f} |")
    lines.append("")
    # NPS delta — usually the headline number.
    b_nps = baseline_agg.get("nps", {}).get("score", 0)
    c_nps = current_agg.get("nps", {}).get("score", 0)
    d_nps = round(c_nps - b_nps, 1)
    lines.append(f"**NPS**: {b_nps} → {c_nps} (Δ {d_nps:+0.1f})")
    lines.append("")
    return "\n".join(lines)


def render_efficiency_themes(evals: list[PersonaEval]) -> str:
    """Render the iteration-3 efficiency_gap + understanding_gap aggregations."""
    eff_responses = [e.efficiency_gap for e in evals if e.efficiency_gap.strip()]
    und_responses = [e.understanding_gap for e in evals if e.understanding_gap.strip()]
    if not eff_responses and not und_responses:
        return ""
    lines = ["## Efficiency + understanding gaps (iteration 3)", ""]
    lines.append(f"_{len(eff_responses)}/{len(evals)} answered the efficiency question; "
                 f"{len(und_responses)}/{len(evals)} answered the understanding question._")
    lines.append("")
    if eff_responses:
        lines.append("### What would help you work faster")
        for phrase, n in _top_phrases(eff_responses, k=10):
            lines.append(f"- *{phrase}* — {n} mentions")
        lines.append("")
        lines.append("### Sample efficiency answers")
        for e in evals[:8]:
            if e.efficiency_gap.strip():
                lines.append(
                    f"**{e.persona.name}** ({e.persona.vibe_experience}/{e.persona.domain_expertise}): {e.efficiency_gap}"
                )
                lines.append("")
    if und_responses:
        lines.append("### What you wish you understood about your session")
        for phrase, n in _top_phrases(und_responses, k=10):
            lines.append(f"- *{phrase}* — {n} mentions")
        lines.append("")
        lines.append("### Sample understanding answers")
        for e in evals[:8]:
            if e.understanding_gap.strip():
                lines.append(
                    f"**{e.persona.name}** ({e.persona.vibe_experience}/{e.persona.domain_expertise}): {e.understanding_gap}"
                )
                lines.append("")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description="50-persona product evaluation")
    parser.add_argument("--label", default="",
                        help="Label appended to output filename "
                             "(e.g. 'iter2'). Default: empty.")
    parser.add_argument("--since", type=float, default=0.0,
                        help="Only sample narrations with timestamp >= this "
                             "unix time. Useful for measuring the effect of "
                             "a specific prompt change.")
    parser.add_argument("--compare-to", default="",
                        help="Path to a previous MARKET_ANALYSIS_*.json. "
                             "Adds a delta-vs-baseline section to the report.")
    parser.add_argument("--efficiency-questions", action="store_true",
                        help="Iteration 3: add two open-ended questions to "
                             "each eval — what would help you work faster, "
                             "and what about your session do you wish you "
                             "understood better that we're not surfacing.")
    args = parser.parse_args()

    api_key = load_api_key()
    log.info("sampling narrations from %s (since_ts=%.0f)", NARRATION_LOG, args.since)
    narrations = sample_narrations(NARRATION_SAMPLE_SIZE, since_ts=args.since)
    if len(narrations) < 3:
        log.error("not enough narrations in log (need 3, have %d). "
                  "If --since is set, the daemon may not have produced any "
                  "live/brief narrations since that timestamp yet.",
                  len(narrations))
        return 1
    log.info("sampled %d narrations across %d (mode,voice) combos",
             len(narrations), len({(n.get("mode"), n.get("voice")) for n in narrations}))

    if args.efficiency_questions:
        log.info("iteration-3 mode: efficiency + understanding questions are ON")

    async with httpx.AsyncClient() as client:
        log.info("generating %d persona batches in parallel (concurrency=%d)",
                 PERSONA_BATCH_COUNT, CONCURRENCY)
        batches = await bounded_gather(
            [gen_persona_batch(client, api_key, BATCH_FOCUSES[i % len(BATCH_FOCUSES)])
             for i in range(PERSONA_BATCH_COUNT)],
            CONCURRENCY,
        )
        personas = [p for batch in batches for p in batch]
        log.info("got %d personas", len(personas))
        if len(personas) < 20:
            log.error("too few personas for meaningful aggregation")
            return 1

        log.info("evaluating personas (concurrency=%d)...", CONCURRENCY)
        eval_results = await bounded_gather(
            [eval_persona(client, api_key, p, narrations,
                          include_efficiency_questions=args.efficiency_questions)
             for p in personas],
            CONCURRENCY,
        )
        evals = [r for r in eval_results if r is not None]
        log.info("got %d/%d valid evals", len(evals), len(personas))

    agg = aggregate(evals)
    report_md = render_report(evals, agg)

    # Compare-to: load baseline, append delta section.
    if args.compare_to:
        try:
            baseline = json.loads(Path(args.compare_to).read_text(encoding="utf-8"))
            delta_md = render_delta(agg, baseline.get("aggregate", {}))
            report_md = report_md.rstrip() + "\n\n" + delta_md
            log.info("appended delta vs %s", args.compare_to)
        except Exception as e:
            log.warning("could not load --compare-to baseline: %s", e)

    # Efficiency section: only when iteration-3 questions were asked.
    if args.efficiency_questions:
        eff_md = render_efficiency_themes(evals)
        if eff_md:
            report_md = report_md.rstrip() + "\n\n" + eff_md

    today = dt.date.today().isoformat()
    suffix = f"-{args.label}" if args.label else ""
    md_path = REPO_ROOT / f"MARKET_ANALYSIS_{today}{suffix}.md"
    json_path = REPO_ROOT / f"MARKET_ANALYSIS_{today}{suffix}.json"
    md_path.write_text(report_md, encoding="utf-8")
    raw = {
        "generated_at": dt.datetime.now().isoformat(),
        "label": args.label,
        "model": MODEL,
        "since_ts": args.since,
        "efficiency_questions": args.efficiency_questions,
        "narration_samples": narrations,
        "aggregate": agg,
        "evals": [
            {**asdict(e), "persona": asdict(e.persona)} for e in evals
        ],
    }
    json_path.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    log.info("wrote %s and %s", md_path.name, json_path.name)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
