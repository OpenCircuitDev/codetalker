// v0.1.0 unification — bottom-right character display pane.
//
// Renders the attached character for the currently-active session as a
// 3D mesh via Google's <model-viewer> (wrapped in ./ModelViewer.tsx for
// React + TS type safety). Daemon serves the GLB at
// `/api/characters/{id}/mesh-file`. Falls back to the persona-tinted
// CharacterAvatar circle when no mesh is available.
//
// Tier 1 ambient animation (this iteration):
//   - auto-rotate via model-viewer (constant slow spin)
//   - cameraOrbit drifts side-to-side over 30s for breathing camera feel
//   - container has `character-breathe` CSS keyframe (1.5% scale, 4.5s)
//   - is_speaking → swap to `character-speak-pulse` (cyan glow + scale)
//   - persona drives a background gradient tint behind the mesh
//   - persona drives `exposure` (warm personas brighter, cool dimmer)
//
// Tier 2 conversational animation (next iteration, design discussion):
//   - "asking a question" → camera leans toward viewer + slight head turn
//   - "pointing out" → camera punch forward + ring highlight
//   - persona-keyed kinetic profiles (sarcastic = off-axis, methodical
//     = ultra-slow, energetic = quick orbits)
//   - narration event-driven momentary highlights
import { useEffect, useMemo, useRef } from "react";
import { useSessions } from "../hooks/useSessions";
import { useCharacterPose } from "../hooks/useCharacterPose";
import { resolveAttachedCharacter, characterDisplayName, getSessionHeadline } from "../types";
import type { AttachedCharacter } from "../types";
import { CharacterAvatar } from "./CharacterAvatar";
import { CharacterMesh } from "./CharacterMeshFallback";
import type { ModelViewerElement } from "./ModelViewer";

type Props = {
  /** Session id of the currently-open detail panel, if any. When set,
   *  this pane shows that session's character. When null, falls back to
   *  any session with a character attached. */
  openSessionId: string | null;
};

// Tier 1 persona kinetic profile. Drives subtle motion + lighting
// without requiring rigged meshes. Keep values gentle — the character
// is an ambient presence, not the focal animation of the screen.
type PersonaProfile = {
  /** Camera-orbit starting point in "<theta> <phi> <radius>" format. */
  cameraOrbit: string;
  /** Degrees per second for auto-rotate. Tier 2 will tune per persona. */
  rotationPerSecond: string;
  /** Tailwind gradient class applied to the stage background, drawn
   *  behind the model-viewer so the mesh sits in a persona-colored
   *  atmosphere. */
  bgGradient: string;
  /** Exposure (1 = neutral). Warm personas push slightly brighter. */
  exposure: string;
};

// v0.1.0 unification — exposure baseline raised so PBR textures from
// Meshy GLBs actually show. With exposure < 1.2 the materials render
// near-flat-gray on the `legacy` HDR. Persona variation rides on top:
// methodical = dimmer (1.3), energetic = brighter (1.7).
const PERSONA_PROFILES: Record<string, PersonaProfile> = {
  methodical: {
    cameraOrbit: "0deg 80deg 110%",
    rotationPerSecond: "12deg",
    bgGradient: "from-slate-900/60 via-slate-950/40 to-blue-950/30",
    exposure: "1.3",
  },
  warm: {
    cameraOrbit: "20deg 75deg 105%",
    rotationPerSecond: "20deg",
    bgGradient: "from-amber-950/40 via-rose-950/30 to-orange-950/20",
    exposure: "1.55",
  },
  technical: {
    cameraOrbit: "-15deg 78deg 108%",
    rotationPerSecond: "15deg",
    bgGradient: "from-cyan-950/40 via-slate-950/40 to-blue-950/30",
    exposure: "1.4",
  },
  plain: {
    cameraOrbit: "0deg 80deg 110%",
    rotationPerSecond: "10deg",
    bgGradient: "from-zinc-900/50 via-zinc-950/40 to-zinc-900/30",
    exposure: "1.4",
  },
  sarcastic: {
    cameraOrbit: "30deg 72deg 105%",
    rotationPerSecond: "18deg",
    bgGradient: "from-fuchsia-950/40 via-purple-950/40 to-violet-950/30",
    exposure: "1.45",
  },
  energetic: {
    cameraOrbit: "-25deg 75deg 100%",
    rotationPerSecond: "28deg",
    bgGradient: "from-rose-900/40 via-orange-950/30 to-amber-950/30",
    exposure: "1.7",
  },
};

const DEFAULT_PROFILE: PersonaProfile = {
  cameraOrbit: "0deg 80deg 110%",
  rotationPerSecond: "15deg",
  bgGradient: "from-zinc-900/50 via-zinc-950/40 to-zinc-900/30",
  exposure: "1.4",
};

function profileFor(persona: string | null | undefined): PersonaProfile {
  if (!persona) return DEFAULT_PROFILE;
  return PERSONA_PROFILES[persona] ?? DEFAULT_PROFILE;
}

/** Drives a slow theta oscillation on the model-viewer's cameraOrbit so
 *  the camera "drifts" left and right around the character. Combined
 *  with auto-rotate this gives a more cinematic ambient feel than pure
 *  rotation alone. Cancels on unmount.
 *
 *  Why not CSS for this: model-viewer's cameraOrbit is a custom prop on
 *  the underlying element, not a CSS transform — needs JS to update. */
function useDriftingCamera(
  ref: React.MutableRefObject<ModelViewerElement | null>,
  profile: PersonaProfile,
  enabled: boolean
) {
  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;
    const baseMatch = profile.cameraOrbit.match(
      /^(-?[\d.]+)deg\s+(-?[\d.]+)deg\s+([\d.]+%?)$/
    );
    if (!baseMatch) return;
    const baseTheta = parseFloat(baseMatch[1]);
    const phi = baseMatch[2];
    const radius = baseMatch[3];
    let raf = 0;
    const start = performance.now();
    const PERIOD_MS = 32_000; // 32s for one full oscillation
    const SWING_DEG = 18; // ±18° around the persona's base theta
    const tick = () => {
      const t = (performance.now() - start) / PERIOD_MS;
      const theta = baseTheta + Math.sin(t * Math.PI * 2) * SWING_DEG;
      el.cameraOrbit = `${theta.toFixed(1)}deg ${phi}deg ${radius}`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ref, profile.cameraOrbit, enabled]);
}

export function CharacterStage({ openSessionId }: Props) {
  const { data: sessions } = useSessions();
  const all = sessions ?? [];

  // v0.1.0 Tier 2 — split focus into two roles:
  //   * displaySession — whose CHARACTER appears in the pane (where the
  //     mesh + persona come from). Sticky to whichever session has one
  //     attached, so the character keeps appearing across the workspace.
  //   * signalSession — whose ACTIVITY drives the animation reactions
  //     (is_speaking, last_user_interaction_at, narration-stream text).
  //     Tracks the user's currently-engaged live session.
  //
  // Why decouple: a character attached to session A should still animate
  // in response to user activity in session B. Coupling them meant Dr.
  // Crow attached to OCRGame stared blank while the user typed in CTDev.
  const opened = openSessionId
    ? all.find((s) => s.session_id === openSessionId) ?? null
    : null;

  const liveWithCharacter = [...all]
    .filter((s) => s.is_live && resolveAttachedCharacter(s.attached_character))
    .sort((a, b) => b.last_modified - a.last_modified)[0];
  const anyWithCharacter = [...all]
    .filter((s) => resolveAttachedCharacter(s.attached_character))
    .sort((a, b) => b.last_modified - a.last_modified)[0];
  // Active live session — our proxy for "the session the user is currently
  // engaged with". last_user_interaction_at is the cleanest signal (bumped
  // on UserPromptSubmit + STT inject); last_modified is the defensive
  // fallback for daemons that don't yet populate the field.
  const activeLive = [...all]
    .filter((s) => s.is_live)
    .sort((a, b) => {
      const aT = a.last_user_interaction_at || a.last_modified;
      const bT = b.last_user_interaction_at || b.last_modified;
      return bT - aT;
    })[0];

  // Display: prefer opened-session iff it has a character, else fall
  // through to the global character chain. This keeps the character
  // visible even when the user clicks a detail panel that has no
  // character attached.
  const displaySession =
    (opened && resolveAttachedCharacter(opened.attached_character)
      ? opened
      : null) ??
    liveWithCharacter ??
    anyWithCharacter ??
    opened ??
    activeLive ??
    null;

  // Signals: the opened session wins (explicit user choice), otherwise the
  // active live session drives reactions. Falls back to displaySession only
  // when there's no live activity at all — so a character can still pose
  // idle against its own dormant session record.
  const signalSession = opened ?? activeLive ?? displaySession ?? null;

  const character: AttachedCharacter | null = displaySession
    ? resolveAttachedCharacter(displaySession.attached_character)
    : null;
  // Header reads "for {headline}" — we show the signal source's headline
  // because that's what the character is REACTING to. When display and
  // signal converge on the same session this is a no-op.
  const headline = signalSession
    ? getSessionHeadline(signalSession)
    : displaySession
    ? getSessionHeadline(displaySession)
    : "";
  const isSpeaking = !!signalSession?.is_speaking;
  const personaProfile = useMemo(
    () => profileFor(character?.persona ?? null),
    [character?.persona]
  );

  // v0.1.0 unification Tier 2 — emotive state machine. Layers a
  // state-driven camera/exposure/rotation override on top of the persona
  // base. When the state is `idle`, persona base wins; when it's
  // `speaking`/`researching`/etc., the StateProfile multipliers shift
  // exposure, slow/quicken rotation, and may override the orbit entirely.
  // Reads from signalSession so the character animates in response to the
  // user's current focus, not whatever session the character is technically
  // attached to.
  const { state: emotive, profile: stateProfile } = useCharacterPose(
    signalSession ?? null
  );

  // Compose the live profile: state override wins on cameraOrbit if set,
  // otherwise the persona base. exposure & rotation are multiplied.
  const profile = useMemo(() => {
    const cameraOrbit = stateProfile.cameraOrbitOverride ?? personaProfile.cameraOrbit;
    const baseExposure = parseFloat(personaProfile.exposure) || 1.0;
    const exposure = (baseExposure * stateProfile.exposureMultiplier).toFixed(2);
    const baseRotMatch = personaProfile.rotationPerSecond.match(/^(-?[\d.]+)deg$/);
    const baseRot = baseRotMatch ? parseFloat(baseRotMatch[1]) : 15;
    const rotation = (baseRot * stateProfile.rotationMultiplier).toFixed(1);
    return {
      ...personaProfile,
      cameraOrbit,
      exposure,
      rotationPerSecond: `${rotation}deg`,
    };
  }, [personaProfile, stateProfile]);

  const mvRef = useRef<ModelViewerElement | null>(null);
  // Drift the camera continuously — gives the character ambient motion
  // beyond auto-rotate (which is just constant spin). When the state
  // overrides cameraOrbit, the drift recenters on the new orbit.
  useDriftingCamera(mvRef, profile, !!(character?.id && character?.mesh_path));

  // Empty state: nothing to display AND nothing to react to. The
  // variable used to be `focused` before the Tier 2 display/signal split
  // — the rename missed this guard, which would have ReferenceError'd
  // the moment a user had zero live sessions.
  if (!displaySession && !signalSession) {
    return (
      <div className="h-full flex items-center justify-center p-4 text-center text-[var(--color-text-3)]">
        <div className="space-y-1">
          <div className="text-sm">No active session</div>
          <div className="text-[11px]">Open a session row to see its character here.</div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={
        "h-full flex flex-col p-4 gap-3 overflow-y-auto relative " +
        "bg-gradient-to-br " +
        profile.bgGradient
      }
    >
      <header className="flex items-baseline justify-between gap-2 min-w-0">
        <h2 className="text-sm font-bold text-[var(--color-text-1)] truncate">
          Character
        </h2>
        <div
          className="text-[10px] text-[var(--color-text-3)] truncate min-w-0"
          title={headline}
        >
          for {headline}
        </div>
      </header>

      {character ? (
        // Mesh fills the available pane height (header is the only
        // sibling). Metadata is overlaid on the bottom of the mesh
        // container as a translucent strip, so the mesh gets the full
        // visual stage instead of being squeezed by stacked text below.
        // The drop-shadow filter applies the emotive state's glow color
        // (cyan for speaking, amber for researching, red for alerted, etc.)
        <div
          className={
            "relative flex-1 min-h-[180px] rounded-lg overflow-hidden bg-black/30 " +
            (isSpeaking ? "character-speak-pulse" : "character-breathe")
          }
          style={
            stateProfile.glowColor
              ? {
                  filter: `drop-shadow(0 0 12px ${stateProfile.glowColor})`,
                  transition: "filter 600ms ease-out",
                }
              : { transition: "filter 600ms ease-out" }
          }
        >
          {character.id && character.mesh_path ? (
            <CharacterMesh
              ref={mvRef}
              src={`/api/characters/${encodeURIComponent(character.id)}/mesh-file`}
              alt={`${characterDisplayName(character)} 3D character`}
              autoRotate
              autoRotateDelay={3000}
              rotationPerSecond={profile.rotationPerSecond}
              cameraControls
              cameraOrbit={profile.cameraOrbit}
              shadowIntensity="1"
              // v0.1.0 unification — texture visibility.
              // `legacy` is model-viewer's built-in warm HDR; gives PBR
              // materials enough light to show embedded textures. With
              // `neutral` the Meshy GLBs render flat-gray. Persona
              // profiles still contribute exposure variation on top.
              exposure={profile.exposure}
              interactionPrompt="auto"
              environmentImage="legacy"
              className="w-full h-full"
              style={{ width: "100%", height: "100%" }}
              fallback={
                <div className="w-full h-full flex items-center justify-center">
                  <CharacterAvatar
                    name={characterDisplayName(character)}
                    characterId={character.id ?? null}
                    persona={character.persona ?? null}
                    size="xl"
                  />
                </div>
              }
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <CharacterAvatar
                name={characterDisplayName(character)}
                characterId={character.id ?? null}
                persona={character.persona ?? null}
                size="xl"
              />
            </div>
          )}

          {/* Optional state-driven overlay (translucent color blended on
              top of the mesh — reinforces the glow signal). */}
          {stateProfile.overlayClass && (
            <div
              className={
                "absolute inset-0 pointer-events-none transition-opacity duration-500 " +
                stateProfile.overlayClass
              }
            />
          )}

          {/* Active emotive state badge — top-right corner, small text.
              Shows what the character is "feeling" right now. Hidden
              for idle (no useful information). */}
          {emotive !== "idle" && (
            <div className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-black/60 text-[9px] uppercase tracking-widest text-cyan-300 font-semibold pointer-events-none">
              {emotive}
            </div>
          )}

          {/* Metadata overlay: translucent footer strip with the
              identifying info, sits over the mesh so the mesh keeps
              the full pane height. */}
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent px-3 pt-6 pb-2 pointer-events-none">
            <div className="flex items-baseline justify-between gap-2 min-w-0">
              <span className="text-sm font-semibold text-[var(--color-text-1)] truncate">
                {characterDisplayName(character)}
              </span>
              {character.persona && (
                <span className="text-[10px] text-[var(--color-text-2)] uppercase tracking-widest shrink-0">
                  {character.persona}
                </span>
              )}
            </div>
            <div className="flex items-center justify-between gap-2 text-[10px] mt-0.5">
              {character.voice_ref && (
                <span className="text-[var(--color-text-3)] font-mono truncate">
                  {character.voice_ref}
                </span>
              )}
              {isSpeaking && (
                <span className="text-cyan-300 font-semibold shrink-0">
                  · speaking
                </span>
              )}
            </div>
            {character.mesh_provider && character.mesh_path && (
              <div className="text-[9px] text-[var(--color-text-3)] mt-0.5">
                3D mesh via <span className="text-cyan-400">{character.mesh_provider}</span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-center text-[var(--color-text-3)]">
          <div className="space-y-1">
            <div className="text-sm">No character attached</div>
            <div className="text-[11px]">
              Open a session's detail panel and pick one from the Library.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
