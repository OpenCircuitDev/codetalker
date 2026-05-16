"""
is_session_audible — the canonical "should this session speak?" function.

This replaces the 5 scattered cfg.get("enabled") checks that lived
across server.py and hooks.py. Every audio-producing code path
asks this single function, and every drop carries a structured
reason that surfaces in /api/audio-jobs/{id} traces and in the
Diagnostics UI.

The audit on 2026-05-16 found 4 separate `enabled` fields the
daemon could read:

  1. state.cfg["enabled"]                  (master, in tts_config.yaml)
  2. session.enabled                       (per-session, in SessionStore)
  3. persistent.enabled                    (per-session, on disk — same as #2 post phase-1)
  4. resolved_cfg["enabled"]               (computed merge of base+overlay)

These could disagree. is_session_audible reads only #1 (master)
and #2 (session) — the canonical pair — and returns the named gate
that fired. No more "skipped: no text" ambiguity.
"""
from __future__ import annotations

from typing import Optional

from claude_code_talker.schemas import AudibleStatus, MasterConfig, Session


def is_session_audible(
    session: Session,
    master: Optional[MasterConfig] = None,
    *,
    require_audio_outputs: bool = True,
) -> AudibleStatus:
    """
    Decide whether this session should produce audio right now.

    Parameters
    ----------
    session: Session
        The canonical session record from SessionStore.
    master: MasterConfig | None
        The global narration config. None is treated as "master
        unset" (audible by default — preserves the daemon's behavior
        in tests that don't construct a full MasterConfig).
    require_audio_outputs: bool
        When True (default), an empty audio_outputs list fails the
        check. Set False when the caller only cares about the
        master/session gates (e.g. the hook handler that produces
        text — whether the text is audible to a SINK is a routing
        concern, not a narration-production concern).

    Returns
    -------
    AudibleStatus
        audible=True with reason="audible" on the happy path.
        audible=False with a named reason when any gate fires.

    Gate evaluation order (first-failing-wins):
      1. master.enabled (master switch off)
      2. session.enabled (per-session muted)
      3. audio_outputs non-empty (when require_audio_outputs=True)

    The order matters: master is the highest-stakes gate (silences
    the fleet) so it's checked first. A muted session is silent
    regardless of master, but if master is off we report master
    as the cause to avoid "I unmuted my session and still no audio"
    confusion.
    """
    # Gate 1: master switch. None master is treated as enabled
    # (test ergonomics — most tests don't construct MasterConfig).
    if master is not None and not master.enabled:
        return AudibleStatus(
            audible=False,
            reason="master_disabled",
            blocking_gate="master.enabled",
        )

    # Gate 2: per-session mute.
    if not session.enabled:
        return AudibleStatus(
            audible=False,
            reason="session_muted",
            blocking_gate="session.enabled",
        )

    # Gate 3: at least one audio sink configured.
    if require_audio_outputs and not session.audio_outputs:
        return AudibleStatus(
            audible=False,
            reason="no_audio_outputs",
            blocking_gate="session.audio_outputs",
        )

    return AudibleStatus(audible=True, reason="audible")
