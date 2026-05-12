// v0.1.0 unification — Tier 2 emotive state machine.
//
// Maps daemon signals (is_speaking, last_modified, narration text shape,
// future hook-event metadata) onto the catalog of canonical states in
// docs/character_emotive_states.md. Each state has a duration, a
// camera/lighting/glow profile, and (Phase 3+) a facial-morph map.
//
// Priority chain (top-of-list wins when multiple fire simultaneously):
//   alerted > speaking > listening > {task states} > idle
//
// Task states (researching/working/questioning/thinking/confirming/
// concluding) are transient — they hold for `durationMs` then decay
// back to idle unless a fresher trigger preempts.
//
// Extensibility — per-character custom prompts: each state has a
// `meshPromptHint` field that future character-creation wizards can
// override per-character. The state machine itself doesn't read these
// (mesh prompts are for generation-time, not runtime), but they live
// alongside the state config so the wizard can introspect.
import { useEffect, useMemo, useRef, useState } from "react";
import { useNarrationStream } from "./useNarrationStream";
import type { Session, NarrationEvent } from "../types";

export type EmotiveState =
  | "idle"
  | "listening"
  | "speaking"
  | "researching"
  | "working"
  | "questioning"
  | "thinking"
  | "confirming"
  | "concluding"
  | "alerted";

export type StateProfile = {
  /** How long this state holds before decaying to idle (transient states).
   *  Set to Infinity for sticky states (speaking, listening, idle). */
  durationMs: number;
  /** "<theta> <phi> <radius>" delta-from-persona-base format.
   *  null means "use persona base unchanged". */
  cameraOrbitOverride: string | null;
  /** Multiplier on persona base exposure. 1.0 = no change. */
  exposureMultiplier: number;
  /** Multiplier on persona base rotation-per-second. */
  rotationMultiplier: number;
  /** Optional CSS color for the drop-shadow glow (around the mesh). */
  glowColor: string | null;
  /** Optional CSS overlay color blended onto the persona background.
   *  Tailwind class fragment like "bg-cyan-500/10". */
  overlayClass: string | null;
  /** Default mesh-prompt hint for generation. Overridable per-character
   *  via the Character.emotive_states custom field map (Phase I8). */
  meshPromptHint: string;
};

export const STATE_PROFILES: Record<EmotiveState, StateProfile> = {
  idle: {
    durationMs: Infinity,
    cameraOrbitOverride: null,
    exposureMultiplier: 1.0,
    rotationMultiplier: 1.0,
    glowColor: null,
    overlayClass: null,
    meshPromptHint:
      "calm neutral pose, eyes forward, mouth closed, gentle breathing",
  },
  listening: {
    durationMs: 5000,
    cameraOrbitOverride: "0deg 75deg 95%",
    exposureMultiplier: 1.15,
    rotationMultiplier: 0.6,
    glowColor: "rgba(59, 130, 246, 0.5)", // blue-500/50
    overlayClass: "bg-blue-500/10",
    meshPromptHint:
      "attentive forward-leaning pose, eyes wide and engaged, mouth slightly parted as if about to respond",
  },
  speaking: {
    durationMs: Infinity,
    cameraOrbitOverride: null,
    exposureMultiplier: 1.1,
    rotationMultiplier: 1.3,
    glowColor: "rgba(34, 211, 238, 0.6)", // cyan-400/60
    overlayClass: "bg-cyan-500/10",
    meshPromptHint:
      "expressive mid-sentence pose, mouth open mid-speech, eyes engaged with viewer, slight forward gesture",
  },
  researching: {
    durationMs: 2500,
    cameraOrbitOverride: "25deg 78deg 115%",
    exposureMultiplier: 0.95,
    rotationMultiplier: 0.5,
    glowColor: "rgba(251, 191, 36, 0.45)", // amber-400/45
    overlayClass: "bg-amber-500/8",
    meshPromptHint:
      "studious focused pose, head tilted reading, eyes narrowed examining something off to the side",
  },
  working: {
    durationMs: 2500,
    cameraOrbitOverride: "0deg 80deg 95%",
    exposureMultiplier: 1.05,
    rotationMultiplier: 0.4,
    glowColor: "rgba(74, 222, 128, 0.5)", // green-400/50
    overlayClass: "bg-green-500/8",
    meshPromptHint:
      "focused working pose, eyes downward at task, mouth set in concentration, hands implied to be active",
  },
  questioning: {
    durationMs: 3000,
    cameraOrbitOverride: "-12deg 74deg 105%",
    exposureMultiplier: 1.05,
    rotationMultiplier: 0.6,
    glowColor: "rgba(167, 139, 250, 0.5)", // violet-400/50
    overlayClass: "bg-violet-500/10",
    meshPromptHint:
      "inquiring head-tilt pose, one eyebrow raised, mouth slightly open mid-question, curious expression",
  },
  thinking: {
    durationMs: 3000,
    cameraOrbitOverride: "15deg 70deg 115%",
    exposureMultiplier: 0.85,
    rotationMultiplier: 0.5,
    glowColor: "rgba(196, 181, 253, 0.4)", // violet-300/40
    overlayClass: "bg-violet-400/6",
    meshPromptHint:
      "contemplative pose, eyes gazing upward in thought, soft pondering expression",
  },
  confirming: {
    durationMs: 2000,
    cameraOrbitOverride: "0deg 80deg 100%",
    exposureMultiplier: 1.2,
    rotationMultiplier: 0.9,
    glowColor: "rgba(74, 222, 128, 0.6)", // green-400/60
    overlayClass: "bg-green-500/12",
    meshPromptHint:
      "satisfied nodding pose, gentle smile, eyes meeting viewer, calm affirming expression",
  },
  concluding: {
    durationMs: 3000,
    cameraOrbitOverride: "0deg 80deg 130%",
    exposureMultiplier: 1.0,
    rotationMultiplier: 0.0, // halt
    glowColor: "rgba(251, 191, 36, 0.5)", // amber-400/50
    overlayClass: "bg-amber-500/8",
    meshPromptHint:
      "settled concluding pose, eyes relaxed, mouth gently closed in satisfaction, body language at ease",
  },
  alerted: {
    durationMs: 2500,
    cameraOrbitOverride: "0deg 80deg 100%",
    exposureMultiplier: 1.25,
    rotationMultiplier: 0.0,
    glowColor: "rgba(239, 68, 68, 0.7)", // red-500/70
    overlayClass: "bg-red-500/15",
    meshPromptHint:
      "alert wide-eyed pose, eyebrows raised in concern, mouth open as if about to warn",
  },
};

/** Text-shape inference for state from narration content. Used as
 *  fallback when the daemon hasn't exposed explicit hook event types
 *  on the narration-stream yet (current state). */
function inferStateFromText(text: string): EmotiveState | null {
  if (!text) return null;
  const t = text.trim();
  // Alert markers — explicit error/warning vocabulary.
  if (/^(Error|Failed|Broken|Stuck|Warning|Help|Wait|Stop|Caught)\b/i.test(t)) {
    return "alerted";
  }
  if (/\bERROR\b/.test(t)) return "alerted";
  // Confirmation markers.
  if (/^(Done|Confirmed|Success|Fixed|Solved|Working|Green|Passed)\b/i.test(t)) {
    return "confirming";
  }
  // Conclusion markers (end-of-task summary phrases).
  if (/^(All set|Wrapping up|Summary|To recap|That's it|We're done)\b/i.test(t)) {
    return "concluding";
  }
  // Question markers.
  if (t.endsWith("?")) return "questioning";
  if (/^(Why|What|How|When|Where|Should|Can|Could|Would|Will|Do|Does)\b/i.test(t)) {
    return "questioning";
  }
  // Thinking markers.
  if (/^(Hmm|Wait|Actually|Let me think|Thinking)\b/i.test(t)) {
    return "thinking";
  }
  return null;
}

/** Decide the active state given current signals + recent narration.
 *  Priority chain matches docs/character_emotive_states.md. */
type StateInput = {
  isSpeaking: boolean;
  lastUserInteractionAt: number; // epoch seconds; 0 if unknown
  transientFromText: { state: EmotiveState; setAt: number } | null;
};

function resolveState(input: StateInput, now: number): EmotiveState {
  // 1. Alerted preempts everything (when transient fired with alerted).
  if (input.transientFromText?.state === "alerted") {
    const elapsed = now - input.transientFromText.setAt;
    if (elapsed < STATE_PROFILES.alerted.durationMs) return "alerted";
  }
  // 2. Speaking is sticky while is_speaking=true.
  if (input.isSpeaking) return "speaking";
  // 3. Listening is sticky while user-interaction is recent.
  // last_user_interaction_at is epoch seconds (from daemon). We treat
  // anything within 5s as "user is engaged right now".
  if (input.lastUserInteractionAt > 0) {
    const ageSec = now / 1000 - input.lastUserInteractionAt;
    if (ageSec < 5) return "listening";
  }
  // 4. Transient task states (text-inferred).
  if (input.transientFromText) {
    const profile = STATE_PROFILES[input.transientFromText.state];
    const elapsed = now - input.transientFromText.setAt;
    if (elapsed < profile.durationMs) return input.transientFromText.state;
  }
  return "idle";
}

/** Top-level pose hook. Subscribes to the daemon's narration stream for
 *  this session, watches the session record's is_speaking +
 *  last_user_interaction_at signals, and exposes the resolved
 *  EmotiveState + its StateProfile. */
export function useCharacterPose(session: Session | null) {
  // narration-stream events filtered to this session.
  const narrationEvents = useNarrationStream(session?.session_id);
  const lastSeenNarrationId = useRef<number>(-1);
  const [transient, setTransient] = useState<{
    state: EmotiveState;
    setAt: number;
  } | null>(null);

  // Watch new narration events and infer transient state from their text.
  useEffect(() => {
    if (narrationEvents.length === 0) return;
    const latestIdx = narrationEvents.length - 1;
    if (latestIdx <= lastSeenNarrationId.current) return;
    lastSeenNarrationId.current = latestIdx;
    const ev: NarrationEvent = narrationEvents[latestIdx];
    if (ev.status !== "speaking" && ev.status !== "done") return;
    const inferred = inferStateFromText(ev.text);
    if (inferred) {
      setTransient({ state: inferred, setAt: performance.now() });
    }
  }, [narrationEvents]);

  // Periodic re-evaluation so transient states decay even when no new
  // signals arrive. 200ms is fine — the state machine is cheap and
  // smooth transitions look better than 1s ticks.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!transient) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 200);
    return () => window.clearInterval(id);
  }, [transient]);
  // referenced so the closure re-fires on tick
  void tick;

  const now = performance.now();
  const state = useMemo<EmotiveState>(() => {
    if (!session) return "idle";
    return resolveState(
      {
        isSpeaking: !!session.is_speaking,
        // Phase I9 — real signal now lives on /api/sessions:
        // last_user_interaction_at is bumped by the daemon on every
        // UserPromptSubmit hook and STT-driven companion inject. 0
        // means "never recorded since daemon start" → not-listening.
        // Falls back to last_modified for old daemons that don't
        // expose the field yet (defensive, no harm if present).
        lastUserInteractionAt:
          session.last_user_interaction_at ?? session.last_modified ?? 0,
        transientFromText: transient,
      },
      now
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.is_speaking, session?.last_modified, transient, tick]);

  const profile = STATE_PROFILES[state];
  return { state, profile };
}

/** Resolve the effective mesh prompt for an emotive state on a specific
 *  character. Per-character `emotive_states[state]` overrides win; falls
 *  back to the global `STATE_PROFILES[state].meshPromptHint`. Used by the
 *  character builder wizard's per-state field rendering AND by the
 *  daemon-side mesh-generation workflow (Phase I12+) when refining or
 *  generating per-state variants.
 *
 *  Example for Dr. Crow (overrides set in his Character.emotive_states):
 *    researching → "scholarly raven peering over half-moon spectacles
 *                   at an ancient tome, dimly lit study"
 *  vs the global default:
 *    researching → "studious focused pose, head tilted reading, eyes
 *                   narrowed examining something off to the side" */
export function resolveStatePrompt(
  character: { emotive_states?: Record<string, string> } | null | undefined,
  state: EmotiveState
): string {
  const override = character?.emotive_states?.[state];
  if (override && override.trim()) return override.trim();
  return STATE_PROFILES[state].meshPromptHint;
}
