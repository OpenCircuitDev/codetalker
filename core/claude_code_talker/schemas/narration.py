"""
NarrationConfig — how a session's text is rendered before TTS.

Markup forms (code fences, inline code, todo updates, etc.), file
paths, and code blocks each have a "treatment" that decides whether
the daemon speaks them verbatim, summarizes them, or skips them.
The legacy YAML format stored these under live_overlay.* with
mixed conventions.

This module formalizes the structure. Every per-session narration
rendering choice has a typed home. Adding a new form means adding
to MARKUP_FORM_KINDS and updating the schema — no more cfg dict
catch-all.
"""
from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# The complete enumeration of markup forms recognized by the pipeline.
# Mirrored from core/claude_code_talker/markup/forms.py::FORM_KINDS.
#
# Each form has a finite set of valid kinds. The kind names overlap
# across forms (e.g. "skip" appears on most) but the *set* of valid
# kinds for each form is form-specific. We validate at runtime against
# the FORM_KINDS table.
# ---------------------------------------------------------------------------

MARKUP_FORM_KINDS: Dict[str, set[str]] = {
    "code_fence":        {"skip", "describe", "read"},
    "inline_code":       {"skip", "identifier_only", "read"},
    "todo_update":       {"skip", "count_only", "itemize", "read"},
    "plan_block":        {"skip", "summarize", "read"},
    "audible_block":     {"speak"},
    "system_reminder":   {"skip", "log_silently"},
    "tool_output":       {"skip", "describe", "read"},
    "subagent_dispatch": {"skip", "announce", "describe"},
    "file_path":         {"skip", "filename", "describe", "read"},
    "long_numeral":      {"skip", "describe", "read"},
}


class MarkupTreatment(BaseModel):
    """
    How one markup form gets rendered before TTS.

      - kind:   the strategy name (must be a member of the form's
                valid kinds; validated dynamically by NarrationConfig).
      - params: strategy-specific parameters (e.g. summarize takes
                max_words; itemize takes max_items). Stored as a
                generic dict because each strategy has its own schema.
    """

    kind: str = Field(
        description=(
            "Treatment strategy. Must be valid for the form this "
            "treatment is bound to (see MARKUP_FORM_KINDS)."
        ),
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy-specific parameters (e.g. {'max_words': 60}).",
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Top-level NarrationConfig — owns the entire rendering config tree
# that previously lived inside live_overlay.
# ---------------------------------------------------------------------------


PathsHandling = Literal["omit", "filename", "full"]
"""How file paths in the transcript are rendered for TTS.
- omit:     skip the path entirely
- filename: read just the leaf (e.g. 'audio.py' instead of full path)
- full:     read every path component
"""

CodeBlocksTreatment = Literal["stub", "full", "summary"]
"""How code blocks are rendered for TTS.
- stub:    "code block omitted"
- full:    read every line
- summary: read a one-sentence description
"""


class NarrationConfig(BaseModel):
    """
    Per-session rendering config. Defaults are conservative (skip-
    heavy) so a session created with bare defaults narrates the
    semantic content, not the noise.
    """

    markup: Dict[str, MarkupTreatment] = Field(
        default_factory=dict,
        description=(
            "Per-form markup treatments. Keys are form names from "
            "MARKUP_FORM_KINDS. Missing keys inherit the master "
            "preset's default for that form."
        ),
    )
    paths_handling: PathsHandling = Field(
        default="filename",
        description="How file paths render in TTS output.",
    )
    code_blocks: CodeBlocksTreatment = Field(
        default="stub",
        description="How code blocks render in TTS output.",
    )

    model_config = {"extra": "forbid"}

    @field_validator("markup")
    @classmethod
    def _validate_markup_kinds(
        cls, v: Dict[str, MarkupTreatment]
    ) -> Dict[str, MarkupTreatment]:
        """
        Verify each treatment's kind is valid for its form. This is
        a model-level check because the validity depends on the key
        (form name), which the per-field validator on MarkupTreatment
        can't see.
        """
        for form, treatment in v.items():
            if form not in MARKUP_FORM_KINDS:
                raise ValueError(
                    f"unknown markup form: {form!r}. Valid forms: "
                    f"{sorted(MARKUP_FORM_KINDS.keys())}"
                )
            if treatment.kind not in MARKUP_FORM_KINDS[form]:
                raise ValueError(
                    f"invalid kind {treatment.kind!r} for form {form!r}. "
                    f"Valid kinds for {form}: {sorted(MARKUP_FORM_KINDS[form])}"
                )
        return v
