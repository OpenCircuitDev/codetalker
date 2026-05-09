import { useState } from "react";
import { CharactersList } from "./CharactersList";
import { CharacterDetail } from "./CharacterDetail";
import { CreateCharacterWizard } from "./CreateCharacterWizard";
import type { Character } from "./characters.types";

export function CharactersTab() {
  const [selected, setSelected] = useState<Character | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  return (
    <div className="grid grid-cols-[280px_1fr] gap-4 h-full">
      <aside className="border-r border-zinc-800 pr-4 space-y-3 overflow-y-auto">
        <header className="flex items-center justify-between">
          <h2 className="font-bold">Characters</h2>
          <button onClick={() => setShowWizard(true)} className="px-2 py-1 bg-cyan-700 text-white rounded text-sm">+ New</button>
        </header>
        <CharactersList selectedId={selected?.id ?? null} onSelect={setSelected} />
      </aside>
      <section className="overflow-y-auto p-2">
        <CharacterDetail character={selected} />
      </section>
      {showWizard && <CreateCharacterWizard onClose={() => setShowWizard(false)} />}
    </div>
  );
}
