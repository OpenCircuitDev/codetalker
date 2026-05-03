"""Tests for virtual_eval.aggregator."""
import pytest
from claude_code_talker.virtual_eval.runner import PersonaScore
from claude_code_talker.virtual_eval.aggregator import (
    aggregate_scores, AggregateReport,
)


def _score(name="A", clarity=4, helpfulness=4, jargon_load=2,
           confusing_terms=None, missing="", narration="x"):
    return PersonaScore(persona_name=name, narration_text=narration,
                        clarity=clarity, helpfulness=helpfulness,
                        jargon_load=jargon_load,
                        confusing_terms=confusing_terms or [],
                        missing_context=missing)


def test_aggregate_empty_returns_empty_report():
    rep = aggregate_scores([])
    assert isinstance(rep, AggregateReport)
    assert rep.total_evals == 0
    assert rep.per_persona == {}


def test_aggregate_per_persona_averages():
    scores = [
        _score(name="A", clarity=5, helpfulness=4),
        _score(name="A", clarity=3, helpfulness=2),
        _score(name="B", clarity=4, helpfulness=4),
    ]
    rep = aggregate_scores(scores)
    assert rep.total_evals == 3
    assert rep.per_persona["A"]["clarity_avg"] == 4.0
    assert rep.per_persona["A"]["helpfulness_avg"] == 3.0
    assert rep.per_persona["B"]["clarity_avg"] == 4.0


def test_aggregate_systemic_jargon_threshold():
    # "CTE" flagged by 3 of 5 personas → systemic
    scores = [
        _score(name=f"P{i}", confusing_terms=["CTE"]) for i in range(3)
    ] + [
        _score(name="P3", confusing_terms=[]),
        _score(name="P4", confusing_terms=["unrelated"]),
    ]
    rep = aggregate_scores(scores, systemic_threshold=3)
    assert "CTE" in rep.systemic_jargon or "cte" in rep.systemic_jargon
    # Threshold met
    assert rep.systemic_jargon.get("cte", rep.systemic_jargon.get("CTE", 0)) == 3


def test_aggregate_excludes_terms_below_threshold():
    scores = [
        _score(name="P0", confusing_terms=["only-one"]),
        _score(name="P1", confusing_terms=[]),
    ]
    rep = aggregate_scores(scores, systemic_threshold=2)
    assert "only-one" not in rep.systemic_jargon


def test_aggregate_collects_missing_context_samples():
    scores = [
        _score(missing="why does this matter?"),
        _score(missing="more about WHY"),
        _score(missing=""),  # blanks ignored
    ]
    rep = aggregate_scores(scores)
    assert len(rep.missing_context_samples) == 2


def test_aggregate_overall_averages():
    scores = [_score(clarity=4, helpfulness=5, jargon_load=2),
              _score(clarity=2, helpfulness=3, jargon_load=4)]
    rep = aggregate_scores(scores)
    assert rep.overall["clarity_avg"] == 3.0
    assert rep.overall["jargon_load_avg"] == 3.0


def test_aggregate_terms_normalized_lowercase():
    scores = [
        _score(name="A", confusing_terms=["CTE"]),
        _score(name="B", confusing_terms=["cte"]),
        _score(name="C", confusing_terms=["Cte"]),
    ]
    rep = aggregate_scores(scores, systemic_threshold=3)
    assert "cte" in rep.systemic_jargon
    assert rep.systemic_jargon["cte"] == 3


def test_aggregate_per_persona_includes_expectation_match_avg():
    """expectation_match averages should appear in per-persona output."""
    scores = [
        PersonaScore(persona_name="A", narration_text="x", clarity=4,
                     helpfulness=4, jargon_load=2, expectation_match=5),
        PersonaScore(persona_name="A", narration_text="x", clarity=4,
                     helpfulness=4, jargon_load=2, expectation_match=3),
    ]
    rep = aggregate_scores(scores)
    assert rep.per_persona["A"]["expectation_match_avg"] == 4.0


def test_aggregate_collects_expectation_gaps():
    """Cases with expectation_match <= 2 surface as actionable gaps."""
    scores = [
        PersonaScore(persona_name="A", narration_text="some narration here",
                     clarity=3, helpfulness=2, jargon_load=4,
                     expectation_match=1, expected="why this matters",
                     received="list of files"),
        PersonaScore(persona_name="B", narration_text="another",
                     clarity=4, helpfulness=4, jargon_load=2,
                     expectation_match=4),  # above threshold, not collected
    ]
    rep = aggregate_scores(scores)
    assert len(rep.expectation_gaps) == 1
    gap = rep.expectation_gaps[0]
    assert gap["persona"] == "A"
    assert gap["expected"] == "why this matters"
    assert gap["received"] == "list of files"
    assert gap["score"] == 1


def test_aggregate_overall_includes_expectation_match():
    scores = [
        PersonaScore(persona_name="A", narration_text="x", clarity=4,
                     helpfulness=4, jargon_load=2, expectation_match=4),
        PersonaScore(persona_name="A", narration_text="x", clarity=4,
                     helpfulness=4, jargon_load=2, expectation_match=2),
    ]
    rep = aggregate_scores(scores)
    assert rep.overall["expectation_match_avg"] == 3.0
