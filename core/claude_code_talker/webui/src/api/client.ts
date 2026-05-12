import type {
  Session,
  SessionConfig,
  SessionOverlayPatch,
  DaemonHealth,
} from "../types";

const BASE = ""; // same-origin; daemon serves /api/* and /ui-react/

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(BASE + url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return (await r.json()) as T;
}

// v0.1.0 unification — fleet audio defaults (single bool flag).
export type AudioDefaults = {
  companion_suppress_desktop: boolean;
  default_outputs: string[];
};

// Character record as returned by GET /api/characters. Locally-cloned
// characters are the v0.1.0 source; mesh_provider tells us whether the
// 3D mesh came from Meshy.ai or a future external platform integration.
export type CharacterRecord = {
  id: string;
  display_name: string;
  persona?: string | null;
  voice_ref?: string | null;
  mesh_path?: string | null;
  mesh_provider?: string | null;
  mesh_prompt?: string | null;
  /** v0.1.0 Tier 2 unification — per-character override map for the
   *  emotive state mesh prompts. Keys are state names from
   *  docs/character_emotive_states.md (idle, listening, speaking,
   *  researching, working, questioning, thinking, confirming,
   *  concluding, alerted). Missing keys fall back to the global
   *  STATE_PROFILES.*.meshPromptHint defaults. */
  emotive_states?: Record<string, string>;
  created_at?: number;
  updated_at?: number;
};

export const api = {
  health: () => fetchJson<DaemonHealth>("/api/health"),
  sessions: () => fetchJson<Session[]>("/api/sessions"),
  sessionConfig: async (id: string): Promise<SessionConfig> => {
    // The daemon's GET /api/sessions/{id} returns a wrapper:
    //   { state: { ... }, resolved_cfg: { voice, active_mode, live, ... } }
    // but useSessionConfig consumers (SessionDetailPanel pickers, mute
    // toggle, etc.) expect the resolved cfg at the top level — so unwrap
    // here. This was the root cause of "voice doesn't save", "Speaking
    // Mode unknown", "Cadence unknown" — every picker was reading from
    // an undefined path.
    const wrapped = await fetchJson<{
      state?: Record<string, unknown>;
      resolved_cfg?: SessionConfig;
    } & SessionConfig>(`/api/sessions/${encodeURIComponent(id)}`);
    // If the response is already flat (older daemon shape), return as-is.
    if (wrapped && typeof wrapped === "object" && "resolved_cfg" in wrapped) {
      return (wrapped.resolved_cfg ?? {}) as SessionConfig;
    }
    return wrapped as SessionConfig;
  },
  putOverlay: async (id: string, overlay: SessionOverlayPatch) => {
    const r = await fetch(`/api/sessions/${encodeURIComponent(id)}/overlay`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(overlay),
    });
    if (!r.ok) throw new Error(`overlay PUT failed: ${r.status}`);
    return r.json();
  },
  audioDefaults: () => fetchJson<AudioDefaults>("/api/cfg/audio-defaults"),
  setAudioDefaults: async (companion_suppress_desktop: boolean) => {
    const r = await fetch("/api/cfg/audio-defaults", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ companion_suppress_desktop }),
    });
    if (!r.ok) throw new Error(`audio-defaults PUT failed: ${r.status}`);
    return r.json() as Promise<AudioDefaults>;
  },
  characters: () => fetchJson<CharacterRecord[]>("/api/characters"),
  attachCharacter: async (sessionId: string, characterId: string) => {
    const r = await fetch(
      `/api/sessions/${encodeURIComponent(sessionId)}/attach-character`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ character_id: characterId }),
      }
    );
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`attach-character ${r.status}: ${text}`);
    }
    return r.json();
  },
  detachCharacter: async (sessionId: string) => {
    const r = await fetch(
      `/api/sessions/${encodeURIComponent(sessionId)}/character`,
      { method: "DELETE" }
    );
    if (!r.ok) throw new Error(`detach-character failed: ${r.status}`);
    return r.json();
  },
};
