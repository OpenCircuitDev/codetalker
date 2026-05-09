import type { Character } from "./characters.types";
import { PersonaBadge } from "./PersonaBadge";

export function CharacterDetail({ character }: { character: Character | null }) {
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
    </div>
  );
}
