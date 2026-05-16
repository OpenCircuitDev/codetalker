"""
AudioJob — a single unit of TTS work, traceable end-to-end.

This is the new audit-trail primitive. Every TTS event the daemon
produces (from a hook, from a buddy inject, from a direct API call)
is wrapped in an AudioJob with a unique job_id. Each gate in the
audio chain records its decision on the job's state_history. After
the chain completes, the job is queryable via /api/audio-jobs/{id}
and the full trace is visible.

This solves the "silent drop" problem. Today's audio chain has 16
gates. Any one can drop the audio and nothing records WHICH. With
AudioJob + state_history, every drop has a structured reason
attached to a specific gate. The user's Diagnostics screen can show
"audio not played because: gate=Strategy-C reason=no_subscribers
at 2026-05-16 15:32:14".
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .enums import AudibleReason, AudioJobState
from .voice import VoiceConfig


class StateTransition(BaseModel):
    """
    A single transition in an AudioJob's state machine. Recorded
    every time the job advances or gets dropped. Together these form
    the audit trail.
    """

    from_state: AudioJobState = Field(
        description="Previous state. 'created' is the initial state.",
    )
    to_state: AudioJobState = Field(
        description="New state. Terminal states are played/skipped/errored.",
    )
    at: float = Field(
        description="Epoch seconds when the transition happened.",
    )
    gate: str = Field(
        description=(
            "Named gate that made the decision. Examples: 'master_check', "
            "'session_enabled_check', 'briefs_check', 'route_decide', "
            "'hub_subscriber_check', 'synth', 'publish'. Used by the "
            "Diagnostics UI to render the trace."
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Short human-readable explanation. For drops, this is the "
            "AudibleReason value or a synth-error message."
        ),
    )


class AudioJob(BaseModel):
    """
    A TTS unit of work, born when something asks the daemon to speak
    and tracked until it plays, is skipped, or errors out.

    Identity:
      job_id is a UUID4 generated at creation. Not user-facing
      directly but appears in Diagnostics + audio-trace API output.

    State machine: see AudioJobState enum. The job advances through
    states linearly except for terminal transitions which can fire
    from any non-terminal state.

    Persistence: kept in memory in a bounded ring buffer (default
    200 most recent jobs). Old jobs evict; current jobs are queryable.
    Not stored in SQLite — these are diagnostic ephemera, not user
    config. If we later want persistent audit logs we add a sink.
    """

    job_id: str = Field(
        description="UUID4 generated at job creation.",
    )
    session_id: str = Field(
        description=(
            "The source session this narration is FOR. May differ from "
            "publish_key when Strategy-C fan-in routes audio to a "
            "different hub key than the source."
        ),
    )
    text: str = Field(
        description=(
            "Final narration text to be synthesized. Includes any "
            "voice-tag prefix (e.g. 'OCRacing: ') prepended by routing."
        ),
    )
    voice: VoiceConfig = Field(
        description="Resolved voice config at the moment of submission.",
    )

    state: AudioJobState = Field(
        default="created",
        description="Current state. Updates only via append_transition().",
    )
    state_history: List[StateTransition] = Field(
        default_factory=list,
        description=(
            "Chronological transitions. The first entry is created→queued, "
            "the last entry is the terminal state. The trace IS this list."
        ),
    )

    created_at: float = Field(
        description="Epoch seconds at job creation.",
    )
    publish_key: Optional[str] = Field(
        default=None,
        description=(
            "Hub key the WAV was published to (set when state advances "
            "to 'publishing'). May differ from session_id for Strategy-C "
            "fan-in. None = job dropped before routing decided."
        ),
    )
    bytes_synthesized: Optional[int] = Field(
        default=None,
        description="WAV size in bytes once synth completed. None until then.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message when state == 'errored'. None otherwise.",
    )

    model_config = {"extra": "forbid"}


class AudibleStatus(BaseModel):
    """
    Return type of is_audible(session, master). Replaces the bare bool
    return from the 5 scattered cfg.get("enabled") checks. Carries the
    REASON so the caller can record it on the AudioJob, surface it in
    the dispatch response, or display it in Diagnostics.
    """

    audible: bool = Field(
        description="True iff this session should produce audio right now.",
    )
    reason: AudibleReason = Field(
        description=(
            "Why it is or isn't audible. 'audible' means the gate passed; "
            "any other value names the gate that rejected it."
        ),
    )
    blocking_gate: Optional[str] = Field(
        default=None,
        description=(
            "When audible=False, which gate raised the objection. Useful "
            "for the Diagnostics UI to render 'this is why you don't hear "
            "audio: ...'."
        ),
    )

    model_config = {"extra": "forbid"}
