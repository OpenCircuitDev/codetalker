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
          <div className="flex items-center gap-2">
            <h2 className="font-bold">Characters</h2>
            <span
              className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-amber-700/40 text-amber-200 border border-amber-600/50 uppercase tracking-wider"
              title="Local voice cloning and animated characters are Pro features."
            >
              Pro
            </span>
          </div>
          <button onClick={() => setShowWizard(true)} className="px-2 py-1 bg-cyan-700 text-white rounded text-sm">+ New</button>
        </header>
        <p className="text-[11px] text-[var(--color-text-3)] leading-snug">
          Local voice cloning and animated characters are Pro features. Web
          creation flows are moving to the Pro Android app in v0.1.x.
        </p>
        <CharactersList selectedId={selected?.id ?? null} onSelect={setSelected} />
      </aside>
      <section className="overflow-y-auto p-2">
        <CharacterDetail character={selected} />
      </section>
      {showWizard && <CreateCharacterWizard onClose={() => setShowWizard(false)} />}
    </div>
  );
}
