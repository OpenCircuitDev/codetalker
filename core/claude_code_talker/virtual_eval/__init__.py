"""Virtual user evaluation for teacher-mode quality + auto-tuning.

Public surface:
    run_eval(...)            - the orchestrator, runs end-to-end
    apply_tuning(...)        - approve a pending_approval proposal
    revert_tuning(...)       - undo a previously-applied tuning
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from claude_code_talker.narration_log import NarrationLog
from claude_code_talker.virtual_eval.aggregator import AggregateReport, aggregate_scores
from claude_code_talker.virtual_eval.auto_tuner import propose_tuning
from claude_code_talker.virtual_eval.history import TuningHistory, TuningEntry
from claude_code_talker.virtual_eval.personas import (
    Persona, build_generation_prompt, parse_personas_response,
)
from claude_code_talker.virtual_eval.runner import (
    EvalRequest, run_eval_batch, select_narration_sample,
)


__all__ = [
    "run_eval", "apply_tuning", "revert_tuning",
    "Persona", "EvalRequest", "AggregateReport", "TuningHistory", "TuningEntry",
]


def _write_overlay_teacher_mode(overlay_path: Path, fields_to_set: dict) -> None:
    """Merge ``fields_to_set`` into overlay_path's teacher_mode block."""
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if overlay_path.exists():
        try:
            existing = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            logging.warning(
                "overlay %s is unparseable (%s); refusing to overwrite to avoid data loss",
                overlay_path, e,
            )
            return  # do not touch a file we can't safely merge into
    if not isinstance(existing, dict):
        existing = {}
    teacher = existing.get("teacher_mode") or {}
    if not isinstance(teacher, dict):
        teacher = {}
    teacher.update(fields_to_set)
    existing["teacher_mode"] = teacher
    tmp = overlay_path.with_suffix(overlay_path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(existing, sort_keys=True), encoding="utf-8")
    os.replace(tmp, overlay_path)  # atomic on POSIX + Windows


async def _generate_personas(provider) -> list[Persona]:
    # 600 was too tight — 5 detailed personas each with name + role +
    # primary_lens + skill_floor + jargon_tolerance + detail_appetite
    # blow past 600 tokens for any non-pithy model. Bumped to 2000 so
    # the JSON array completes; cheap on Haiku/openrouter.
    raw = await provider.complete(build_generation_prompt(), max_tokens=2000)
    return parse_personas_response(raw)


async def run_eval(
    *,
    narration_log: NarrationLog,
    history: TuningHistory,
    current_cfg: dict,
    provider,
    overlay_path: Path,
    catalog=None,  # SessionCatalog | None — used for transcript context
    deployed_at: float = 0.0,
    max_narrations: int = 50,
) -> dict:
    """Run an end-to-end virtual user eval.

    1. Sample narrations from ``narration_log`` since ``deployed_at``
    2. For each sampled narration, gather session context (prior narrations,
       last user prompt, recent transcript turns) via virtual_eval.context
    3. Generate 5 personas via ``provider``
    4. Score every (persona, narration_with_context) pair — personas see the
       narration in its session context, not in isolation
    5. Aggregate scores into a report
    6. Ask provider for a tuning proposal grounded in the aggregate
    7. If under max-divergence gate -> write to overlay + history (applied=True)
       Otherwise -> write to history only (applied=False)

    Returns a dict suitable for JSON-serializing in the REST response.
    """
    from claude_code_talker.virtual_eval.context import gather_context_for_narration
    sample_dicts = select_narration_sample(narration_log, EvalRequest(
        max_narrations=max_narrations, deployed_at=deployed_at,
    ))
    if not sample_dicts:
        return {
            "personas_count": 0, "narrations_evaluated": 0,
            "aggregate": {"total_evals": 0},
            "proposal": {"fields_to_set": {}, "reasoning": "", "pending_approval": False},
            "applied": False,
        }
    # Enrich every sampled narration with its session context so personas can
    # score in context (per user correction 2026-05-03 evening).
    sample_with_context = [
        gather_context_for_narration(d, narration_log, catalog=catalog)
        for d in sample_dicts
    ]
    try:
        personas = await _generate_personas(provider)
    except Exception as e:
        logging.warning("persona generation failed: %s", e)
        return {
            "personas_count": 0, "narrations_evaluated": len(sample_with_context),
            "aggregate": {"total_evals": 0},
            "proposal": {"fields_to_set": {}, "reasoning": "", "pending_approval": False},
            "applied": False, "error": f"personas: {e}",
        }
    scores = await run_eval_batch(personas, sample_with_context, provider)
    report = aggregate_scores(scores)
    proposal = await propose_tuning(report, current_cfg, provider)

    applied = False
    if proposal["fields_to_set"] and not proposal["pending_approval"]:
        # Compute "before" snapshot for the history entry
        before = {k: current_cfg.get(k) for k in proposal["fields_to_set"].keys()}
        history.append(
            before=before, after=proposal["fields_to_set"],
            reasoning=proposal["reasoning"], applied=True,
        )
        _write_overlay_teacher_mode(overlay_path, proposal["fields_to_set"])
        applied = True
    elif proposal["fields_to_set"] and proposal["pending_approval"]:
        before = {k: current_cfg.get(k) for k in proposal["fields_to_set"].keys()}
        history.append(
            before=before, after=proposal["fields_to_set"],
            reasoning=proposal["reasoning"], applied=False,
        )
    return {
        "personas_count": len(personas),
        "narrations_evaluated": len(sample_with_context),
        "aggregate": {
            "total_evals": report.total_evals,
            "per_persona": report.per_persona,
            "systemic_jargon": report.systemic_jargon,
            "missing_context_samples": report.missing_context_samples,
            "overall": report.overall,
        },
        "proposal": proposal,
        "applied": applied,
    }


def apply_tuning(
    *, history: TuningHistory, entry_id: str, overlay_path: Path,
) -> bool:
    """Approve a pending_approval entry: write its fields to overlay AND mark
    it applied in a NEW history entry (the original stays as the request).

    Returns True on success; False if entry not found.
    """
    entry = history.get(entry_id)
    if entry is None or entry.applied:
        return False
    _write_overlay_teacher_mode(overlay_path, entry.after)
    history.append(
        before=entry.before, after=entry.after,
        reasoning=f"approved by user (originally proposed {entry.id})", applied=True,
    )
    return True


def revert_tuning(
    *, history: TuningHistory, entry_id: str, overlay_path: Path,
) -> bool:
    """Apply the inverse of an applied entry: write entry.before to overlay
    AND record the revert as a new history entry."""
    entry = history.get(entry_id)
    if entry is None or not entry.applied:
        return False
    _write_overlay_teacher_mode(overlay_path, entry.before)
    history.append(
        before=entry.after, after=entry.before,
        reasoning=f"revert of {entry.id}", applied=True,
    )
    return True
