// Phase 27 — character info embedded in a session, when attached.
// v0.1.0 unification — display_name is now OPTIONAL because the daemon
// may serialize a stub `{id, display_name: id}` for stale references
// (character was deleted but session still points to it). Components
// should fall back to `id` for the headline when display_name is missing.
export type AttachedCharacter = {
  id?: string;
  display_name?: string;
  persona?: string | null;
  voice_ref?: string | null;
  mesh_path?: string | null;
  mesh_provider?: string | null;
};

/** Normalize the `attached_character` field — older/legacy daemons send
 *  a bare string ID, newer daemons send the full record. Always returns
 *  either null or a fully-typed AttachedCharacter so components don't
 *  have to guard against both shapes. */
export function resolveAttachedCharacter(
  value: string | AttachedCharacter | null | undefined
): AttachedCharacter | null {
  if (value == null) return null;
  if (typeof value === "string") {
    if (!value.trim()) return null;
    return { id: value, display_name: value };
  }
  return value;
}

/** Resolve a character's user-visible name. Prefers display_name,
 *  falls back to the id (which is what the resolver above stuffs into
 *  display_name when given a bare string), then a literal "?". */
export function characterDisplayName(c: AttachedCharacter | null | undefined): string {
  if (!c) return "";
  return c.display_name ?? c.id ?? "?";
}

// v0.1.0 unification — discrete audio sinks. Empty array = silenced
// everywhere; null/undefined = inherit fleet default.
export type AudioOutput = "desktop" | "phone" | "glasses";

/** Resolve a session's user-visible headline. Forward declaration of
 *  Session is fine since this only reads two fields. The fallback to
 *  `slice(0, 8)` matches the daemon's last-resort behavior in
 *  api.py's list_sessions handler. */
export function getSessionHeadline(s: { display_name?: string; session_id: string }): string {
  return s.display_name || s.session_id.slice(0, 8);
}

// Mirror of the JSON shape returned by GET /api/sessions
export type Session = {
  session_id: string;
  cwd: string;
  project_slug: string;
  /**
   * @deprecated CCT-28: the backend's resolved `display_name` is the
   * canonical headline — `title` is the raw auto-title and must not be
   * consumed by the UI. Kept here only because the fixture in
   * SessionCard.test.tsx still asserts the regression. Remove once the
   * test no longer references it.
   */
  title?: string;
  display_name: string;
  last_modified: number;
  is_live: boolean;
  enabled: boolean;
  attached_profile: string | null;
  has_persistent_settings: boolean;
  // Phase 27 — optional fields populated when known.
  // v0.1.0 unification — accept either a bare ID string (legacy daemons)
  // or the resolved record. Always pipe through resolveAttachedCharacter.
  attached_character?: string | AttachedCharacter | null;
  is_speaking?: boolean;
  is_muted?: boolean;
  mode?: string;
  // v0.1.0 unification — fields exposed on /api/sessions to match the
  // Pro Android session model. All optional; null/missing means
  // "inherit fleet default" or "ungrouped".
  audio_outputs?: AudioOutput[] | null;
  auto_mode_enabled?: boolean;
  auto_mode_idle_threshold_secs?: number | null;
  workspace_group?: string | null;
  project_dir?: string | null;
  /** v0.1.0 unification — pin-to-top within the session's workspace group.
   *  When true, sorts ahead of other sessions in the same group. Persisted
   *  in the daemon overlay so it syncs across webui + Pro Android. */
  pinned?: boolean;
  /** v0.1.0 Tier 2 — epoch seconds of last UserPromptSubmit or buddy
   *  inject for this session. Drives the CharacterStage's `listening`
   *  state. 0 = never seen since daemon start (treated as not-listening).
   *  Transient — wiped on daemon restart, refreshed by next hook. */
  last_user_interaction_at?: number;
  // CCT-28 cat 3: removed `events?: SessionTickerEvent[]`. The backend never
  // populated this field; the dead per-card LiveTicker block was removed.
  // The global LiveTicker in ActivityTab feeds from the SSE stream instead.
};

// Mirror of GET /api/sessions/{id} — per-session config overlay (resolved cfg).
export type SessionConfig = {
  enabled: boolean;
  preset?: string;
  voice?: { engine?: string; model?: string; rate?: number };
  active_mode?: string;
  // CCT-28 cat 4 — cadence is nested under cfg.live.cadence on the wire
  // (see static/app.js's "live.cadence" overlay key); overlay PUTs send
  // `{ live: { cadence: "<value>" } }`.
  live?: {
    cadence?: string;
    significance_threshold?: number;
  };
};

// v0.1.0 unification — every key the daemon's _merge_into_persistent
// recognizes when PUT /api/sessions/{id}/overlay is called. The wire
// format mixes session-level fields (display_name, workspace_group,
// audio_outputs, auto_mode_*) with config-level fields (enabled,
// active_mode, voice, live.cadence). Anything else falls into the
// `live_overlay` bucket on the daemon side.
export type SessionOverlayPatch = Partial<SessionConfig> & {
  display_name?: string | null;
  workspace_group?: string | null;
  audio_outputs?: AudioOutput[] | null;
  auto_mode_enabled?: boolean;
  auto_mode_idle_threshold_secs?: number | null;
  pinned?: boolean;
};

// Phase 23 — narration stream event
export type NarrationEvent = {
  session_id: string;
  timestamp: number;
  text: string;
  voice: string;
  mode: string;
  status: "queued" | "speaking" | "done" | "skipped" | "overflow";
};

export type DaemonHealth = { ok: boolean };
