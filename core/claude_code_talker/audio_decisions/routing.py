"""
route_audio_publish_key — decide which hub key to publish a WAV on.

Wraps the existing multi_session_routing.decide_multi_session_route
in a Session-aware API. Phase 6 will delete the old function once
all callers go through this one.

Why a wrapper instead of replacing the old function directly: the
existing decide_multi_session_route is keyword-only with primitive
inputs (job_session_id: str, opted_in_sessions: list[str], etc.).
Callers all over audio.py construct those primitives from the
current state.sessions / state.persistent_sessions. The wrapper
takes the canonical Session list directly, makes the routing
decision typed, and emits the existing RoutingDecision so the
audio worker can swap to it without re-architecting the worker
loop in this phase.
"""
from __future__ import annotations

from typing import List, Optional

from claude_code_talker.companion.multi_session_routing import (
    RoutingDecision,
    decide_multi_session_route,
)
from claude_code_talker.schemas import Session


def route_audio_publish_key(
    job_session: Session,
    *,
    all_sessions: List[Session],
    companion_active_session_id: Optional[str],
    last_played_session_id: Optional[str],
    now: float,
) -> RoutingDecision:
    """
    Given a job's source Session and the current state, decide the
    hub key the WAV should be published to.

    Wraps decide_multi_session_route by computing opted_in_sessions
    from the canonical Session list (no more reads from
    state.persistent_sessions on the audio hot path).

    Returns
    -------
    RoutingDecision
        publish_to_session_id is the hub key. Empty string means
        "drop this audio" — caller surfaces that as a "skipped:
        no_subscribers" reason on the AudioJob trace.
    """
    # opted_in = sessions whose audio_outputs include phone or glasses.
    # The companion path requires at least one such sink; if none
    # exist, the routing falls through to source-sid (see
    # multi_session_routing.py).
    opted_in = [
        s.session_id
        for s in all_sessions
        if any(o in {"phone", "glasses"} for o in s.audio_outputs)
    ]

    return decide_multi_session_route(
        job_session_id=job_session.session_id,
        job_workspace_group=job_session.workspace_group,
        opted_in_sessions=opted_in,
        companion_active_session=companion_active_session_id,
        last_played_session_id=last_played_session_id,
        now=now,
    )
