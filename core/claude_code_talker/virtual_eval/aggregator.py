"""Aggregate persona scores into actionable report data."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from claude_code_talker.virtual_eval.runner import PersonaScore


@dataclass
class AggregateReport:
    total_evals: int = 0
    per_persona: dict[str, dict] = field(default_factory=dict)
    systemic_jargon: dict[str, int] = field(default_factory=dict)
    missing_context_samples: list[str] = field(default_factory=list)
    # Expectation gap samples: persona, narration_excerpt, expected, received,
    # score (the expectation_match int). Tuples where expectation_match <= 2 —
    # these are the most actionable signals for refining teacher mode.
    expectation_gaps: list[dict] = field(default_factory=list)
    overall: dict[str, float] = field(default_factory=dict)


def aggregate_scores(
    scores: list[PersonaScore], *, systemic_threshold: int = 3,
) -> AggregateReport:
    """Roll up raw persona scores into a structured report.

    - per_persona: per-persona averages of clarity/helpfulness/jargon_load/expectation_match
    - systemic_jargon: terms flagged by >= ``systemic_threshold`` distinct personas
    - missing_context_samples: non-blank missing-context strings (deduped, capped)
    - expectation_gaps: cases where expectation_match <= 2 with the persona's
      expected vs received strings
    - overall: cross-cohort averages
    """
    rep = AggregateReport()
    rep.total_evals = len(scores)
    if not scores:
        return rep

    # Per-persona aggregates
    by_persona: dict[str, list[PersonaScore]] = defaultdict(list)
    for s in scores:
        by_persona[s.persona_name].append(s)
    for name, items in by_persona.items():
        n = len(items)
        rep.per_persona[name] = {
            "n": n,
            "clarity_avg": round(sum(s.clarity for s in items) / n, 2),
            "helpfulness_avg": round(sum(s.helpfulness for s in items) / n, 2),
            "jargon_load_avg": round(sum(s.jargon_load for s in items) / n, 2),
            "expectation_match_avg": round(sum(s.expectation_match for s in items) / n, 2),
        }

    # Expectation gaps: collect cases where the persona's expected ≠ received
    # (expectation_match <= 2 → score 1 or 2, meaning miles off)
    for s in scores:
        if s.expectation_match <= 2 and (s.expected or s.received):
            rep.expectation_gaps.append({
                "persona": s.persona_name,
                "narration_excerpt": s.narration_text[:120],
                "expected": s.expected,
                "received": s.received,
                "score": s.expectation_match,
            })
        if len(rep.expectation_gaps) >= 30:
            break

    # Systemic jargon — count DISTINCT personas flagging each term
    term_to_personas: dict[str, set[str]] = defaultdict(set)
    for s in scores:
        for term in s.confusing_terms:
            normalized = term.strip().lower()
            if normalized:
                term_to_personas[normalized].add(s.persona_name)
    rep.systemic_jargon = {
        term: len(personas)
        for term, personas in term_to_personas.items()
        if len(personas) >= systemic_threshold
    }

    # Missing-context samples (dedup + cap)
    seen: set[str] = set()
    for s in scores:
        m = s.missing_context.strip()
        if m and m.lower() not in seen:
            seen.add(m.lower())
            rep.missing_context_samples.append(m)
        if len(rep.missing_context_samples) >= 30:
            break

    # Overall averages
    n = len(scores)
    rep.overall = {
        "clarity_avg": round(sum(s.clarity for s in scores) / n, 2),
        "helpfulness_avg": round(sum(s.helpfulness for s in scores) / n, 2),
        "jargon_load_avg": round(sum(s.jargon_load for s in scores) / n, 2),
        "expectation_match_avg": round(sum(s.expectation_match for s in scores) / n, 2),
    }
    return rep
