// Phase 27 — Global activity log. Aggregates the existing /api/narration-stream
// SSE feed (which already fans across all sessions) into the LiveTicker UI.
//
// CCT-28 cat 3: previously this tab opened its own EventSource alongside any
// consumer of useNarrationStream (e.g. the NarrationFeed rail), so the
// daemon received two SSE subscriptions while the tab was visible. We now
// reuse the shared hook and adapt NarrationEvent -> TickerEvent in a
// useMemo, so there is exactly one subscription per page.
import { useMemo } from "react";
import { LiveTicker, type TickerEvent } from "../../components/LiveTicker";
import { useNarrationStream } from "../../hooks/useNarrationStream";

const KIND_FROM_STATUS: Record<string, string> = {
  speaking: "speak",
  done: "speak",
  queued: "speak",
  skipped: "tool",
  overflow: "error",
};

const ACTIVITY_BUFFER = 300;

export function ActivityTab() {
  const narrationEvents = useNarrationStream(undefined, ACTIVITY_BUFFER);
  const events = useMemo<TickerEvent[]>(
    () =>
      narrationEvents.map((ev, i) => ({
        id: `${ev.session_id}:${ev.timestamp}:${i}`,
        kind: KIND_FROM_STATUS[ev.status] || "system",
        text: ev.text || `(${ev.status})`,
        ts: (ev.timestamp || Date.now() / 1000) * 1000,
        alert: ev.alert,
        checkpoint: ev.checkpoint,
      })),
    [narrationEvents],
  );

  return (
    <div className="h-full p-4 flex flex-col">
      <header className="mb-3">
        <h2 className="text-lg font-bold text-[var(--color-text-1)]">Activity</h2>
        <p className="text-sm text-[var(--color-text-3)]">
          Global narration feed across all sessions.
        </p>
      </header>
      <div className="flex-1 min-h-[400px] bg-[var(--color-surface-1)] rounded border border-zinc-800 overflow-hidden">
        <LiveTicker events={events} maxEvents={ACTIVITY_BUFFER} />
      </div>
    </div>
  );
}
