// Phase 27 — filterable ticker feed of SSE events.
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { tickerEntry } from "../theme/motion";

export interface TickerEvent {
  id: string;
  kind: string; // "speak" | "tool" | "system" | "error" | "subagent"
  text: string;
  ts: number;
}

const FILTER_OPTIONS = [
  { kind: "all", label: "All", color: "bg-zinc-700" },
  { kind: "speak", label: "Speak", color: "bg-emerald-700" },
  { kind: "tool", label: "Tool", color: "bg-cyan-700" },
  { kind: "subagent", label: "Subagent", color: "bg-violet-700" },
  { kind: "error", label: "Error", color: "bg-rose-700" },
];

export function LiveTicker({
  events,
  maxEvents = 100,
}: {
  events: TickerEvent[];
  maxEvents?: number;
}) {
  const [filter, setFilter] = useState("all");
  const filtered = useMemo(() => {
    const list = filter === "all" ? events : events.filter((e) => e.kind === filter);
    return list.slice(-maxEvents);
  }, [events, filter, maxEvents]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 p-2 border-b border-zinc-800">
        {FILTER_OPTIONS.map((o) => (
          <button
            key={o.kind}
            onClick={() => setFilter(o.kind)}
            className={
              "px-2 py-0.5 rounded text-xs " +
              (filter === o.kind
                ? o.color + " text-white"
                : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")
            }
          >
            {o.label}
          </button>
        ))}
      </div>
      <ul key={filter} className="flex-1 overflow-y-auto p-2 space-y-1">
        {filtered.length === 0 && (
          <li className="text-zinc-500 italic text-sm">
            It's quiet. Waiting for activity…
          </li>
        )}
        <AnimatePresence initial={false}>
          {filtered.map((e) => (
            <motion.li
              key={e.id}
              variants={tickerEntry}
              initial="initial"
              animate="animate"
              exit="exit"
              className="text-sm p-1 rounded bg-[var(--color-surface-2)] flex gap-2 items-center"
            >
              <span
                className={
                  "inline-block px-1.5 rounded text-xs uppercase " + kindBg(e.kind)
                }
              >
                {e.kind}
              </span>
              <span className="flex-1 truncate">{e.text}</span>
              <span className="text-zinc-500 text-xs whitespace-nowrap">
                {new Date(e.ts).toLocaleTimeString().slice(0, 8)}
              </span>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}

function kindBg(kind: string): string {
  switch (kind) {
    case "speak":
      return "bg-emerald-700 text-emerald-100";
    case "tool":
      return "bg-cyan-700 text-cyan-100";
    case "subagent":
      return "bg-violet-700 text-violet-100";
    case "error":
      return "bg-rose-700 text-rose-100";
    default:
      return "bg-zinc-700 text-zinc-100";
  }
}
