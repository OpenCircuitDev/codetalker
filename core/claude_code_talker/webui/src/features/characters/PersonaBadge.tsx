import type { Persona } from "./characters.types";

const PERSONA_COLORS: Record<Persona, string> = {
  methodical: "bg-slate-700 text-slate-100",
  warm: "bg-amber-700 text-amber-100",
  technical: "bg-cyan-700 text-cyan-100",
  plain: "bg-zinc-700 text-zinc-100",
  sarcastic: "bg-fuchsia-700 text-fuchsia-100",
  energetic: "bg-rose-700 text-rose-100",
};

export function PersonaBadge({ persona }: { persona: Persona | null }) {
  if (!persona) return <span className="text-zinc-500 text-xs italic">no persona</span>;
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${PERSONA_COLORS[persona]}`}>
      {persona}
    </span>
  );
}
