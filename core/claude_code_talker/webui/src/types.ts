// Phase 27 — character info embedded in a session, when attached.
export type AttachedCharacter = {
  id?: string;
  display_name: string;
  persona?: string | null;
  voice_ref?: string | null;
  mesh_path?: string | null;
};

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
  attached_character?: AttachedCharacter | null;
  is_speaking?: boolean;
  is_muted?: boolean;
  mode?: string;
  // CCT-28 cat 3: removed `events?: SessionTickerEvent[]`. The backend never
  // populated this field; the dead per-card LiveTicker block was removed.
  // The global LiveTicker in ActivityTab feeds from the SSE stream instead.
};

// Mirror of GET /api/sessions/{id} — per-session config overlay
export type SessionConfig = {
  enabled: boolean;
  preset?: string;
  voice?: { engine?: string; model?: string; rate?: number };
  active_mode?: string;
  cadence?: string;
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
