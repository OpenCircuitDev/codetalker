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
    # === Per-session routing (Strategy A, simplified) ===
    #
    # 2026-05-17 — dropped the lex-first fan-in. The previous code routed
    # every opted-in session's audio onto `companion_active_session`, which
    # was set deterministically to `sorted(companion_active_sessions)[0]`
    # by companion/api.py. That meant only the lex-first session's hub
    # subscription ever received bytes — every other "active" session on
    # the phone got silence. With multiple sessions active (e.g. CodeTalker
    # 87b24267 + BF Skills 96e480c1), the lex-first sid (87b24267) owned
    # the entire pipe and all BF Skills audio got published to the wrong
    # hub key, never reaching the BF Skills subscription. That was the
    # multi-day silence pattern.
    #
    # The phone subscribes to N hub keys via setActiveSessions() and the
    # Android TTSPlayer fans them in client-side. So the daemon should
    # just publish each session's audio to that session's own hub key.
    # No lex-ownership, no silent subscriptions.
    #
    # The `companion_active_session` and `last_played_session_id`
    # parameters are kept in the signature for backwards-compat with
    # callers, but no longer influence the publish key.
    if not opted_in_sessions:
        return RoutingDecision(
            publish_to_session_id=job_session_id,
            intro_text="",
        )
    if job_session_id not in opted_in_sessions:
        return RoutingDecision(publish_to_session_id="")
    # Intro tag identifies the speaker when MULTIPLE sessions could be
    # heard simultaneously, but only when the speaker just changed (so
    # a chatty session doesn't repeat "BF Skills: ... BF Skills: ...").
    intro = ""
    if (
        len(opted_in_sessions) > 1
        and job_session_id != last_played_session_id
    ):
        intro = _short_tag(job_workspace_group)
    return RoutingDecision(
        publish_to_session_id=job_session_id,
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
