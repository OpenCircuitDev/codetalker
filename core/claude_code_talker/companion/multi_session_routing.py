"""CCT-32 v0.1.0 unification — multi-session audio routing strategy.

When a single user (single AR companion pairing) has multiple live Claude
Code sessions opted-in to phone/glasses audio output via their
`audio_outputs` overlay, the daemon needs a policy for which session's
audio reaches the phone subscriber at any given moment.

This is a USER-SHAPED decision: the right behavior depends on whether the
user wants to hear everything at once (overlap), one at a time (queue),
or focus on a "primary" session with brief notifications about the others.

The function below is the single decision point. Audio worker calls it
right before publishing a WAV. The returned action tells the worker
what to do.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class RoutingDecision:
    """What the audio worker should do with this WAV for the phone path."""

    # Where to publish the WAV: a session_id key on the audio_hub. The phone
    # subscribes per session_id, so this controls whose stream gets the bytes.
    # Set to the empty string to skip the companion path entirely.
    publish_to_session_id: str

    # Optional short voice intro to prepend so the listener knows whose
    # session is speaking (e.g., "OCR-Web:"). Empty = no intro.
    intro_text: str = ""

    # If the strategy wants to delay this WAV (queue behavior), set seconds
    # > 0. Worker will sleep + retry. 0.0 = play immediately.
    delay_secs: float = 0.0


def decide_multi_session_route(
    *,
    job_session_id: str,
    job_workspace_group: str | None,
    opted_in_sessions: list[str],
    companion_active_session: str | None,
    last_played_session_id: str | None,
    now: float,
) -> RoutingDecision:
    """Pick the routing for this audio job in a multi-session world.

    Parameters
    ----------
    job_session_id
        The session that produced this WAV.
    job_workspace_group
        That session's user-assigned workspace group (e.g., "OCDev").
    opted_in_sessions
        All live session_ids whose `audio_outputs` contains "phone" or
        "glasses" — i.e., the candidate pool the phone could hear.
    companion_active_session
        The session the user explicitly marked "active" on the phone (the
        one whose audio-stream the TTSPlayer is currently subscribed to).
    last_played_session_id
        Which session's audio was most recently routed to the phone. Useful
        for round-robin or last-wins strategies.
    now
        Current wall clock (seconds since epoch). Useful if you want to
        implement a "primary session for the last 10s" rule.

    Returns
    -------
    RoutingDecision
        See dataclass docstring.

    --------------------------------------------------------------------
    TODO (user-shaped strategy): implement the policy that fits the user's
    listening model. Pick ONE approach (or combine):

      A) "Active-only" (simplest, matches today): only route audio whose
         job_session_id == companion_active_session. Others fall on the
         floor for the companion. ~3 lines.

      B) "Fan-in to active": publish ALL opted-in sessions' audio to the
         companion_active_session's stream, with intro_text = session name.
         Hear everything via a single subscription, with voice tags.
         ~5 lines.

      C) "Round-robin queue": keep a deque elsewhere; this function consults
         it. Each call routes to the head of the queue. ~10 lines + state.

      D) "Recent-talker wins": route to whichever session has been quiet
         longest, so no single session monopolizes the listener. Needs to
         read each session's last_published_at.

    Write the body below, replacing the `raise NotImplementedError`.
    """
    # === Strategy C with graceful fallback ===
    #
    # AudioQueue is single-threaded and FIFO, so the natural order is
    # already serial. We fan EVERY opted-in session's audio into the
    # companion_active_session's hub key so the phone (subscribed to that
    # one stream) hears them all in turn. A short voice tag prefix tells
    # the listener which workspace is currently speaking.
    #
    # 2026-05-16 — when companion_active_session is unset (e.g. fresh
    # daemon, phone hasn't pushed its DataStore-restored active set yet,
    # or a non-paired install is just consuming hub bytes), fall back to
    # publishing on the SOURCE session's own key. That preserves audio
    # for the simple case ("phone subscribes to TEST-OCR-Web, hears
    # TEST-OCR-Web's narration") while keeping the round-robin behavior
    # active whenever an active session IS set. Treat it as "Strategy A
    # if no active set, Strategy C if there is one" — both honor the
    # session's audio_outputs opt-in.
    # 2026-05-16 (phase 1 refactor): when NO session has opted into
    # multi-session routing (the common case for fresh installs and
    # for any session whose persistent overlay doesn't set
    # audio_outputs), fall through to source-sid routing instead of
    # dropping. Previously this case dropped the audio silently —
    # which made "no audio" the default outcome until a user
    # explicitly configured per-session audio_outputs.
    if not opted_in_sessions:
        return RoutingDecision(
            publish_to_session_id=job_session_id,
            intro_text="",
        )
    if job_session_id not in opted_in_sessions:
        return RoutingDecision(publish_to_session_id="")
    if not companion_active_session:
        return RoutingDecision(
            publish_to_session_id=job_session_id,
            intro_text="",
        )
    # Drop the intro when the same session speaks twice in a row — avoids
    # repeating "OCDev: ... OCDev: ..." for a chatty session.
    intro = ""
    if job_session_id != last_played_session_id:
        intro = _short_tag(job_workspace_group)
    return RoutingDecision(
        publish_to_session_id=companion_active_session,
        intro_text=intro,
    )


def _short_tag(workspace_group: str | None) -> str:
    """One-word voice prefix so the listener identifies the speaker.

    Returns "" when the source session has no workspace_group — better
    silence than reading a long auto-generated label aloud.
    """
    if not workspace_group:
        return ""
    return f"{workspace_group}: "
