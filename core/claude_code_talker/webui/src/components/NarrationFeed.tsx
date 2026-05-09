// Phase 27 — narration rail. Subscribes to /api/narration-stream.
import { useNarrationStream } from "../hooks/useNarrationStream";

const STATUS_COLORS: Record<string, string> = {
  queued: "text-slate-400",
  speaking: "text-emerald-300",
  done: "text-slate-500",
  skipped: "text-rose-400",
  overflow: "text-amber-400",
};

export function NarrationFeed() {
  const events = useNarrationStream();
  if (events.length === 0) {
    return (
      <div className="p-4 text-xs text-[var(--color-text-3)]">
        Live narration feed will appear here.
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto font-mono text-xs">
      {events
        .slice()
        .reverse()
        .map((ev, i) => (
          <div
            key={`${ev.timestamp}-${i}`}
            className="flex items-baseline gap-2 px-4 py-1 hover:bg-zinc-900/40"
          >
            <span className={STATUS_COLORS[ev.status] ?? "text-slate-400"}>
              {ev.status.padEnd(8)}
            </span>
            <span className="text-slate-500">{ev.session_id.slice(0, 8)}</span>
            <span className="text-slate-200 truncate">{ev.text || "—"}</span>
          </div>
        ))}
    </div>
  );
}
