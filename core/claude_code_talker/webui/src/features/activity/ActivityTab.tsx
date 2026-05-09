// Phase 27 — Global activity log. Aggregates the existing /api/narration-stream
// SSE feed (which already fans across all sessions) into the LiveTicker UI.
import { useEffect, useState } from "react";
import { LiveTicker, type TickerEvent } from "../../components/LiveTicker";
import type { NarrationEvent } from "../../types";

const KIND_FROM_STATUS: Record<string, string> = {
  speaking: "speak",
  done: "speak",
  queued: "speak",
  skipped: "tool",
  overflow: "error",
};

export function ActivityTab() {
  const [events, setEvents] = useState<TickerEvent[]>([]);

  useEffect(() => {
    const es = new EventSource("/api/narration-stream");
    let counter = 0;
    es.onmessage = (m) => {
      try {
        const ev = JSON.parse(m.data) as NarrationEvent;
        const ticker: TickerEvent = {
          id: `${ev.session_id}:${ev.timestamp}:${counter++}`,
          kind: KIND_FROM_STATUS[ev.status] || "system",
          text: ev.text || `(${ev.status})`,
          ts: (ev.timestamp || Date.now() / 1000) * 1000,
        };
        setEvents((cur) => {
          const next = [...cur, ticker];
          return next.length > 300 ? next.slice(-300) : next;
        });
      } catch {
        /* ignore malformed events */
      }
    };
    return () => es.close();
  }, []);

  return (
    <div className="h-full p-4 flex flex-col">
      <header className="mb-3">
        <h2 className="text-lg font-bold text-[var(--color-text-1)]">Activity</h2>
        <p className="text-sm text-[var(--color-text-3)]">
          Global narration feed across all sessions.
        </p>
      </header>
      <div className="flex-1 min-h-[400px] bg-[var(--color-surface-1)] rounded border border-zinc-800 overflow-hidden">
        <LiveTicker events={events} maxEvents={300} />
      </div>
    </div>
  );
}
