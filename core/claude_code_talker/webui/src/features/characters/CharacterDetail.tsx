import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Character } from "./characters.types";
import { PersonaBadge } from "./PersonaBadge";
import { attachCharacter } from "./characters.api";
import { MeshGenerator } from "./MeshGenerator";
import { EmotiveStatesEditor } from "./EmotiveStatesEditor";

interface SessionLite {
  session_id: string;
  display_name?: string;
  /** @deprecated CCT-28 — falling through to title showed raw user-message text. Use display_name. */
  title?: string;
}

async function fetchSessions(): Promise<SessionLite[]> {
  const r = await fetch("/api/sessions");
  if (!r.ok) return [];
  const data = await r.json();
  // /api/sessions may return a list or {sessions: [...]} depending on version.
  if (Array.isArray(data)) return data as SessionLite[];
  if (data && Array.isArray(data.sessions)) return data.sessions as SessionLite[];
  return [];
}

export function CharacterDetail({ character }: { character: Character | null }) {
  const { data: sessions = [] } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    enabled: !!character,
  });
  const qc = useQueryClient();
  const attach = useMutation({
    mutationFn: ({ sessionId, characterId }: { sessionId: string; characterId: string }) =>
      attachCharacter(sessionId, characterId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });

  // v0.1.0 Tier 2 — save updated emotive_states map via PUT /api/characters/{id}.
  // The endpoint accepts the full character record, so we merge the new
  // emotive_states into the existing record and PUT the whole thing.
  const saveEmotive = useMutation({
    mutationFn: async (next: Record<string, string>) => {
      if (!character) throw new Error("no character");
      const body = { ...character, emotive_states: next };
      const r = await fetch(`/api/characters/${encodeURIComponent(character.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const t = await r.text().catch(() => "");
        throw new Error(`PUT character ${r.status}: ${t}`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["characters"] });
    },
  });

  if (!character) return <p className="text-zinc-500">Select a character to see details.</p>;
  return (
    <div className="space-y-3">
      <header>
        <h2 className="text-xl font-bold">{character.display_name}</h2>
        <p className="text-zinc-400 text-sm">{character.id}</p>
        <PersonaBadge persona={character.persona} />
      </header>
      <dl className="text-sm space-y-1">
        <div><dt className="text-zinc-500 inline">voice_ref:</dt> <dd className="inline">{character.voice_ref}</dd></div>
        {character.mesh_path && <div><dt className="text-zinc-500 inline">mesh:</dt> <dd className="inline">{character.mesh_path}</dd></div>}
        <div><dt className="text-zinc-500 inline">created:</dt> <dd className="inline">{new Date(character.created_at * 1000).toLocaleString()}</dd></div>
      </dl>
      <div className="space-y-1 pt-3 border-t border-zinc-800">
        <p className="text-zinc-500 text-sm">Attach to session:</p>
        <select
          className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm"
          defaultValue=""
          onChange={(e) => {
            if (e.target.value) attach.mutate({ sessionId: e.target.value, characterId: character.id });
          }}
        >
          <option value="">- pick session -</option>
          {sessions.map((s) => {
            // CCT-28 fix (extends commit f77078f to all session-label sites):
            // trust the backend's display_name. Falling through to s.title
            // here had been showing raw first-user-message text instead of
            // the slug/customTitle.
            const label = (s.display_name || s.session_id.slice(0, 8)).slice(0, 60);
            return (
              <option key={s.session_id} value={s.session_id}>
                {label}
              </option>
            );
          })}
        </select>
        {attach.isError && (
          <p className="text-rose-400 text-xs">{(attach.error as Error)?.message}</p>
        )}
        {attach.isSuccess && (
          <p className="text-emerald-400 text-xs">attached</p>
        )}
      </div>
      <MeshGenerator characterId={character.id} />
      <EmotiveStatesEditor
        value={character.emotive_states}
        onChange={(next) => saveEmotive.mutate(next)}
        saving={saveEmotive.isPending}
      />
      {saveEmotive.isError && (
        <p className="text-rose-400 text-xs">
          {(saveEmotive.error as Error)?.message}
        </p>
      )}
    </div>
  );
}
