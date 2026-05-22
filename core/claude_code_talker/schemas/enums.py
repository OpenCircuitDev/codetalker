"""
Enum-like Literal types used across the schema.

These are the canonical sets of valid values for fields that need
finite, well-typed choices. Defining them here once means clients
(webui TypeScript, Pro Kotlin) see the exact same set after codegen.

Decisions captured here came from explicit user direction on
2026-05-16 during the architecture refactor:

  * SpeakingMode: 4 first-class modes (live / brief / direct / teacher).
    2026-05-17 migration: "teacher" added after the Android ModePicker
    began offering it as a peer of the others and the auto-tuner began
    configuring teacher_mode cfg. Symptoms before migration: setting a
    session to "teacher" via ModePicker → daemon's SessionView Pydantic
    validation rejected it → /api/companion/sessions returned HTTP 500
    → entire Android session list disappeared every time the user
    touched mode settings. The "conscious decision" anticipated in the
    earlier docstring is this one.

  * AudioOutput: unordered set, multiple sinks receive audio
    simultaneously. The list value is treated as a set; order does
    not imply priority. This matches the user's mental model of
    "I want narration here AND here".

  * SessionLifecycle: 4 explicit states. The LISTENING state is the
    AR/XR-relevant one — drives character avatar pose between user
    prompt and assistant reply. Without it the avatar can't react
    distinctly to "user is asking me something" vs "I am idle".

  * MasterPreset: enumerated to match the preset bundles defined in
    presets.py. Adding a new preset requires updating both files,
    which is exactly the friction we want — presets are user-facing
    documented modes, not implementation details.
"""
from __future__ import annotations

from typing import Literal


# ---------------------------------------------------------------------------
# Speaking mode — per-session narration verbosity.
# ---------------------------------------------------------------------------

SpeakingMode = Literal["live", "brief", "direct", "teacher", "critical_only"]
"""
- live:    continuous prose narration with cadence-driven mid-response speech
- brief:   short one-sentence summaries at significant events only
- direct:  tool-output-as-spoken (terse, immediate, no LLM rewrite)
- teacher: live-style continuous narration re-framed for a non-expert
           audience via the per-session teacher_mode config (depth_level,
           substitution, glossary, reframe, prompt_directive_extras).
           Backend strategy: ride the existing LiveMode pipeline with the
           teacher_mode cfg block applied at prompt-build time. Pro
           ModePicker has offered this since CCT-32 v0.1.0 polish.
- critical_only: narrates ONLY when something matters — errors, blockers,
           completed major tasks, or sessions needing user input. Everything
           else stays silent. One-click option for "alert mode" users.

These are the only modes the schema validates. Hook handlers, mode
pickers, and routing logic all read this Literal and must handle
every value. Adding a new mode requires:
  1. Add to this Literal.
  2. Implement the mode strategy in core/claude_code_talker/modes/.
  3. Regenerate webui + Pro Android client types.
  4. Update Pro Android ModePicker.MODE_OPTIONS.
  5. Migrate any persistent overlays that need the new mode as default.
"""


# ---------------------------------------------------------------------------
# Audio output sink — where narration audio physically plays.
# ---------------------------------------------------------------------------

AudioOutput = Literal["desktop", "phone", "glasses"]
"""
- desktop: daemon plays the WAV on the local machine via OS audio.
           No companion subscription needed; immediate playback.
- phone:   daemon publishes the WAV to audio_hub keyed by session_id;
           the paired companion app's TTSPlayer fetches and plays.
- glasses: same hub publish as phone, but a future USB-Audio detection
           on the Beam Pro can route this stream to the XREAL One Pro
           audio jack distinct from the phone speaker. Today routes
           identically to phone; the schema reserves the distinction
           so AR/XR wiring (phase 7) does not require a schema change.

Treatment is unordered: a Session.audio_outputs of {"desktop", "phone"}
means both sinks play simultaneously. There is no priority/fallback.
"""


# ---------------------------------------------------------------------------
# Session lifecycle — explicit state machine.
# ---------------------------------------------------------------------------

SessionLifecycle = Literal["SPEAKING", "LISTENING", "IDLE", "DORMANT"]
"""
Explicit state machine that REPLACES the implicit is_live + is_speaking
+ recently_active fan-out we have today. The daemon is the only writer;
clients render based on this single field.

Transitions:
  DORMANT  → IDLE       on first hook (UserPromptSubmit, PreToolUse, etc.)
  IDLE     → LISTENING  on UserPromptSubmit (user typed; awaiting reply)
  LISTENING → SPEAKING  on AudioJob entering Synthesizing/Publishing
  SPEAKING → IDLE       on AudioJob terminal state (Played/Skipped/Errored)
  IDLE     → LISTENING  on next UserPromptSubmit
  IDLE     → DORMANT    after IDLE_TIMEOUT_SEC of no activity (default 3600)
  any      → DORMANT    on explicit eviction (sweeper or user action)

LISTENING is the AR/XR character-avatar driver: the glasses HUD shows
"thinking" pose distinct from "idle" pose distinct from "speaking" pose.
SessionLifecycle drives that.
"""


# ---------------------------------------------------------------------------
# Cadence — how often live-mode emits mid-response narration.
# ---------------------------------------------------------------------------

Cadence = Literal[
    "periodic",
    "per_tool_call",
    "per_cluster",
    "significant_only",
    "hybrid",
]
"""
Only meaningful when active_mode == "live". The Pro Android ModePicker
hides cadence when mode != live; webui dims it. The daemon's live mode
strategies in core/claude_code_talker/cadence/ each implement one of
these.
"""


# ---------------------------------------------------------------------------
# Master preset — top-level bundle that defines defaults.
# ---------------------------------------------------------------------------

MasterPreset = Literal[
    "monitor",
    "synopsis",
    "conclusions",
    "brief",
    "verbose",
]
"""
Defined in core/claude_code_talker/presets.py. Each preset is a deep-
merge of defaults under user config. monitor is the production default.
"""


# ---------------------------------------------------------------------------
# Voice engine — TTS provider.
# ---------------------------------------------------------------------------

VoiceEngine = Literal[
    "piper",
    "edge",
    "elevenlabs",
    "openai",
    "xtts",
]
"""
Each engine is registered in core/claude_code_talker/engines/. The
audio worker resolves the engine by name; if a voice model isn't
available on the configured engine, falls back to piper's first voice.
"""


# ---------------------------------------------------------------------------
# Device type — for pairing + subscription routing.
# ---------------------------------------------------------------------------

DeviceType = Literal["phone", "glasses", "webui"]
"""
- phone:   Pro Android app on a paired companion device.
- glasses: XREAL One Pro (or similar AR display). Future phase 7.
- webui:   browser session viewing the React dashboard.

Pairing tokens carry device_type so the daemon can route caption
rendering vs audio-only vs HUD distinctly.
"""


# ---------------------------------------------------------------------------
# AudioJob state machine — explicit lifecycle for every TTS unit of work.
# ---------------------------------------------------------------------------

AudioJobState = Literal[
    "created",
    "queued",
    "routing",
    "synthesizing",
    "publishing",
    "played",
    "skipped",
    "errored",
]
"""
Every AudioJob walks this state machine. Each transition is recorded
in StateTransition (see audio_job.py) with timestamp + reason. The
audit trail makes "why didn't I hear that" answerable in one query.

Terminal states: played, skipped, errored. Once reached, no further
transitions.
"""


# ---------------------------------------------------------------------------
# Audible reason — why a session is or isn't currently audible.
# ---------------------------------------------------------------------------

AudibleReason = Literal[
    "audible",
    "master_disabled",
    "session_muted",
    "no_audio_outputs",
    "no_subscribers",
    "no_voice",
    "no_text",
    "briefs_disabled",
    "auto_mode_silent",
]
"""
Returned by is_audible(session, master) in audio_decisions.py (phase 2).
Replaces the 5 different "skipped: no text" returns scattered across
hook handlers. Every drop has a named, structured reason that surfaces
in the AudioJob trace and the Diagnostics UI.
"""


# ---------------------------------------------------------------------------
# Character pose — for AR/XR avatar driving.
# ---------------------------------------------------------------------------

CharacterPose = Literal[
    "idle",
    "listening",
    "speaking",
    "thinking",
    "researching",
    "working",
    "questioning",
    "confirming",
    "concluding",
    "alerted",
]
"""
The emotive state machine documented at docs/character_emotive_states.md.
Drives glasses HUD avatar render. Computed by the daemon from
SessionLifecycle + event semantics; clients subscribe to
CharacterPoseChanged events (see events.py) and update the avatar.
"""
