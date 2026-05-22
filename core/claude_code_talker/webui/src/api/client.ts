import type {
  Session,
  SessionConfig,
  SessionOverlayPatch,
  DaemonHealth,
  MasterEnabled,
} from "../types";

// Mirror of the daemon's Pydantic SessionPatch
// (schemas/patches.py:SessionPatch). All fields optional; unknown
// fields are rejected by the daemon with 400. Phase 5 will generate
// this type from the Pydantic schema directly.
export type SessionPatchPayload = {
  display_name?: string;
  workspace_group?: string;
  active_mode?: "live" | "brief" | "direct";
  cadence?:
    | "periodic"
    | "per_tool_call"
    | "per_cluster"
    | "significant_only"
    | "hybrid";
  enabled?: boolean;
  auto_mode_enabled?: boolean;
  audio_outputs?: ("desktop" | "phone" | "glasses")[];
  voice?: { engine?: string; model?: string; rate?: number };
  attached_profile?: string;
  attached_character?: {
    id: string;
    display_name: string;
    voice_ref?: string;
    persona?: string;
    mesh_path?: string | null;
    mesh_provider?: string | null;
    mesh_prompt?: string | null;
  };
  pinned?: boolean;
};

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
  // 2026-05-16 -- master narration switch. GET reads the current value;
  // setMasterEnabled persists to tts_config.yaml so the change survives
  // daemon restart and propagates to the Pro Android Preferences toggle
  // through the same /api/health response.
  masterEnabled: () => fetchJson<MasterEnabled>("/api/master-enabled"),
  setMasterEnabled: async (enabled: boolean) => {
    const r = await fetch(`/api/master-enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!r.ok) throw new Error(`setMasterEnabled -> ${r.status}`);
    return (await r.json()) as MasterEnabled;
  },
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
  // Phase 3 (2026-05-16) — typed entry point that mirrors the daemon's
  // SessionPatch schema. Use this for session-level field writes
  // (mute, mode, cadence, audio_outputs, workspace_group, pinned,
  // attached_profile, attached_character). Returns the fresh
  // SessionView so the caller can skip a follow-up GET.
  //
  // The legacy putOverlay still works and is required for the markup
  // form treatments (nested under live_overlay.markup) — SessionPatch
  // doesn't carry that key yet; Phase 5 schema codegen will close
  // that last gap.
  patchSession: async (
    id: string,
    partial: SessionPatchPayload,
  ): Promise<Session> => {
    const r = await fetch(`/api/sessions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(partial),
    });
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`patchSession ${r.status}: ${text}`);
    }
    return (await r.json()) as Session;
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
  audioRewind: async (seconds: number = 30, sessionId?: string) => {
    const r = await fetch("/api/audio/rewind", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seconds, ...(sessionId ? { session_id: sessionId } : {}) }),
    });
    if (!r.ok) throw new Error(`rewind POST failed: ${r.status}`);
    return r.json() as Promise<{ requeued: number; skipped_dupes: number; message?: string }>;
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
