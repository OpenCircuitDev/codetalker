import type { Session, SessionConfig, DaemonHealth } from "../types";

const BASE = ""; // same-origin; daemon serves /api/* and /ui-react/

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(BASE + url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  health: () => fetchJson<DaemonHealth>("/api/health"),
  sessions: () => fetchJson<Session[]>("/api/sessions"),
  sessionConfig: (id: string) =>
    fetchJson<SessionConfig>(`/api/sessions/${encodeURIComponent(id)}`),
  putOverlay: async (id: string, overlay: Partial<SessionConfig>) => {
    const r = await fetch(`/api/sessions/${encodeURIComponent(id)}/overlay`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(overlay),
    });
    if (!r.ok) throw new Error(`overlay PUT failed: ${r.status}`);
    return r.json();
  },
};
