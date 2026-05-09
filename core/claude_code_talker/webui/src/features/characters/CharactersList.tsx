import { useQuery } from "@tanstack/react-query";
import { listCharacters } from "./characters.api";
import { PersonaBadge } from "./PersonaBadge";
import type { Character } from "./characters.types";

export function CharactersList({ selectedId, onSelect }: { selectedId: string | null; onSelect: (c: Character) => void }) {
  const { data: chars = [], isLoading } = useQuery({ queryKey: ["characters"], queryFn: listCharacters });
  if (isLoading) return <p className="text-zinc-500">Loading...</p>;
  if (chars.length === 0) return <p className="text-zinc-500 text-sm">No characters yet. Click + to create.</p>;
  return (
    <ul className="space-y-1">
      {chars.map(c => (
        <li key={c.id}>
          <button
            onClick={() => onSelect(c)}
            className={`w-full text-left px-3 py-2 rounded border ${
              selectedId === c.id ? "bg-zinc-800 border-cyan-600" : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            <div className="font-medium">{c.display_name}</div>
            <div className="text-xs text-zinc-400">{c.id}</div>
            <PersonaBadge persona={c.persona} />
          </button>
        </li>
      ))}
    </ul>
  );
}
