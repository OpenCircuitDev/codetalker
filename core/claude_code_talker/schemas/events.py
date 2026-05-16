"""
Domain events — what the daemon publishes when state changes.

Phase 4 of the refactor introduces an SSE endpoint at /api/events
that streams these events to subscribed clients. Both the webui and
the Pro Android app subscribe instead of poll, dropping the 8
polling loops we have today.

Every event has:
  - `event_type` discriminator (matches SSE event: prefix)
  - `at` timestamp
  - Event-specific payload fields

Clients filter by event_type. The Pro Android Sessions list cares
about SessionChanged and LifecycleChanged. The webui Diagnostics
view cares about AudioJobStateChanged. The glasses HUD (phase 7)
cares about CharacterPoseChanged.
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from .enums import AudioJobState, CharacterPose, SessionLifecycle


# ---------------------------------------------------------------------------
# Base event — every event has a type and a timestamp.
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """
    Base class for all SSE events. Pydantic discriminated unions
    (using `event_type` as the discriminator) let clients deserialize
    into the right subtype.
    """

    event_type: str = Field(
        description="Discriminator. SSE event: prefix matches this.",
    )
    at: float = Field(
        description="Epoch seconds when the event was emitted.",
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# SessionChanged — a session's fields changed.
# ---------------------------------------------------------------------------


class SessionChanged(Event):
    """
    Emitted when SessionStore.update writes any non-empty patch. The
    payload is the diff: only fields that changed. Clients merge into
    their local snapshot.
    """

    event_type: Literal["SessionChanged"] = "SessionChanged"
    session_id: str
    changed_fields: Dict[str, Any] = Field(
        description=(
            "Field name → new value, for every field that changed in "
            "this write. Order does not imply causality."
        ),
    )


# ---------------------------------------------------------------------------
# LifecycleChanged — explicit transition between SPEAKING/LISTENING/IDLE/DORMANT.
# ---------------------------------------------------------------------------


class LifecycleChanged(Event):
    """
    Distinct from SessionChanged because lifecycle drives AR/XR
    avatar pose and we want consumers to subscribe to JUST these
    without filtering through every SessionChanged. The phone +
    glasses use this directly; the webui mostly ignores it (renders
    lifecycle as a colored dot from the snapshot instead).
    """

    event_type: Literal["LifecycleChanged"] = "LifecycleChanged"
    session_id: str
    from_state: SessionLifecycle
    to_state: SessionLifecycle


# ---------------------------------------------------------------------------
# AudioJobStateChanged — an audio job advanced or terminated.
# ---------------------------------------------------------------------------


class AudioJobStateChanged(Event):
    """
    Surfaces every audio gate decision. Diagnostics UIs subscribe to
    these to render the trace. Production UIs ignore most of these
    (they're high-frequency) and only watch for terminal states to
    update the "speaking" indicator.
    """

    event_type: Literal["AudioJobStateChanged"] = "AudioJobStateChanged"
    job_id: str
    session_id: str
    from_state: AudioJobState
    to_state: AudioJobState
    gate: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# MasterConfigChanged — the global narration switch (or any master field) changed.
# ---------------------------------------------------------------------------


class MasterConfigChanged(Event):
    """
    The master narration switch or any other MasterConfig field
    changed. All UIs (webui status bar pill, Pro Sessions header
    pill, Pro Preferences row) update their toggle state from this.
    """

    event_type: Literal["MasterConfigChanged"] = "MasterConfigChanged"
    changed_fields: Dict[str, Any]


# ---------------------------------------------------------------------------
# SubscriptionChanged — a device subscribed or unsubscribed to a session's audio stream.
# ---------------------------------------------------------------------------


class SubscriptionChanged(Event):
    """
    Emitted when a device opens or closes its audio_hub poller for a
    session. Lets the daemon's audio worker know if synth is worth
    doing (no subscribers = skip synth). Surfaced in Diagnostics so
    the user can see "phone has 2 active subscriptions".
    """

    event_type: Literal["SubscriptionChanged"] = "SubscriptionChanged"
    session_id: str
    subscriber_count: int
    delta: Literal[1, -1]
    device_type: Optional[str] = Field(
        default=None,
        description="Which device type joined/left. Useful for glasses-vs-phone routing.",
    )


# ---------------------------------------------------------------------------
# CharacterPoseChanged — drives AR/XR avatar render.
# ---------------------------------------------------------------------------


class CharacterPoseChanged(Event):
    """
    The character avatar's pose should transition. Computed by the
    daemon from SessionLifecycle + audio job state + event semantics.

    Defined now (during stabilization) even though only the glasses
    HUD will subscribe (phase 7). The schema being ready means
    phase 7 doesn't require a daemon change — it just adds the
    client-side renderer.
    """

    event_type: Literal["CharacterPoseChanged"] = "CharacterPoseChanged"
    session_id: str
    character_id: str
    pose: CharacterPose
