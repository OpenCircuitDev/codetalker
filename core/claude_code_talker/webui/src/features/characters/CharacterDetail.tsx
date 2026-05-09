import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Character } from "./characters.types";
import { PersonaBadge } from "./PersonaBadge";
import { attachCharacter } from "./characters.api";

interface SessionLite { session_id: string; title?: string }

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
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.title || s.session_id.slice(0, 8)}
            </option>
          ))}
        </select>
        {attach.isError && (
          <p className="text-rose-400 text-xs">{(attach.error as Error)?.message}</p>
        )}
        {attach.isSuccess && (
          <p className="text-emerald-400 text-xs">attached</p>
        )}
      </div>
    </div>
  );
}
