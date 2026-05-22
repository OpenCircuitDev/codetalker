// Phase 27 — filterable ticker feed of SSE events.
import { useMemo, useState, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { tickerEntry } from "../theme/motion";

export interface TickerEvent {
  id: string;
  kind: string; // "speak" | "tool" | "system" | "error" | "subagent"
  text: string;
  ts: number;
  alert?: boolean;  // true when something broke, blocked, or needs input
  checkpoint?: boolean;  // true for architectural decision checkpoints
}

const FILTER_OPTIONS = [
  { kind: "all", label: "All", color: "bg-zinc-700" },
  { kind: "speak", label: "Speak", color: "bg-emerald-700" },
  { kind: "tool", label: "Tool", color: "bg-cyan-700" },
  { kind: "subagent", label: "Subagent", color: "bg-violet-700" },
  { kind: "error", label: "Error", color: "bg-rose-700" },
];

const CHECKPOINT_FILTER_OPTIONS = [
  { mode: "all-events", label: "All Events", color: "bg-zinc-700" },
  { mode: "decisions-only", label: "Decisions Only", color: "bg-amber-700" },
];

export function LiveTicker({
  events,
  maxEvents = 100,
}: {
  events: TickerEvent[];
  maxEvents?: number;
}) {
  const [filter, setFilter] = useState("all");
  const [checkpointFilter, setCheckpointFilter] = useState("all-events");
  const filterRowRef = useRef<HTMLDivElement>(null);
  const checkpointRowRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    let list = filter === "all" ? events : events.filter((e) => e.kind === filter);
    if (checkpointFilter === "decisions-only") {
      list = list.filter((e) => e.checkpoint === true);
    }
    return list.slice(-maxEvents);
  }, [events, filter, checkpointFilter, maxEvents]);

  // Handle arrow-key navigation within filter pill rows
  const handleFilterKeyDown = (
    e: React.KeyboardEvent,
    rowRef: React.RefObject<HTMLDivElement | null>,
    currentValue: string,
    options: typeof FILTER_OPTIONS | typeof CHECKPOINT_FILTER_OPTIONS,
    setter: (val: string) => void
  ) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const currentIndex = options.findIndex((o) =>
        "kind" in o ? o.kind === currentValue : o.mode === currentValue
      );
      const next =
        e.key === "ArrowRight"
          ? (currentIndex + 1) % options.length
          : (currentIndex - 1 + options.length) % options.length;
      const nextValue = "kind" in options[next] ? options[next].kind : options[next].mode;
      setter(nextValue);
      // Focus the newly selected button
      setTimeout(() => {
        const buttons = rowRef.current?.querySelectorAll("button");
        if (buttons) buttons[next]?.focus();
      }, 0);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-col gap-2 p-2 border-b border-zinc-800">
        <div
          ref={filterRowRef}
          className="flex items-center gap-1"
          role="group"
          aria-label="Event filter"
        >
          {FILTER_OPTIONS.map((o) => (
            <button
              key={o.kind}
              onClick={() => setFilter(o.kind)}
              onKeyDown={(e) =>
                handleFilterKeyDown(e, filterRowRef, filter, FILTER_OPTIONS, setFilter)
              }
              aria-pressed={filter === o.kind}
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
        <div
          ref={checkpointRowRef}
          className="flex items-center gap-1"
          role="group"
          aria-label="Checkpoint filter"
        >
          {CHECKPOINT_FILTER_OPTIONS.map((o) => (
            <button
              key={o.mode}
              onClick={() => setCheckpointFilter(o.mode)}
              onKeyDown={(e) =>
                handleFilterKeyDown(
                  e,
                  checkpointRowRef,
                  checkpointFilter,
                  CHECKPOINT_FILTER_OPTIONS,
                  setCheckpointFilter
                )
              }
              aria-pressed={checkpointFilter === o.mode}
              className={
                "px-2 py-0.5 rounded text-xs " +
                (checkpointFilter === o.mode
                  ? o.color + " text-white"
                  : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")
              }
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <ul key={`${filter}:${checkpointFilter}`} className="flex-1 overflow-y-auto p-2 space-y-1">
        {filtered.length === 0 && (
          <li className="text-zinc-500 italic text-sm">
            {checkpointFilter === "decisions-only"
              ? "No architectural checkpoints in this window. The narrator emits these when it commits to a schema, API shape, dependency, or migration approach."
              : "It's quiet. Waiting for activity…"}
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
              {e.alert && (
                <span
                  className="inline-block px-1.5 rounded text-xs uppercase font-semibold bg-red-500/30 text-red-100 border border-red-500/50"
                  title="Alert: something broke, blocked, or needs input"
                  aria-label="Alert"
                >
                  <span aria-hidden="true">⚠</span> alert
                </span>
              )}
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
