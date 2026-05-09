import { useEffect, useState } from "react";
import type { NarrationEvent } from "../types";

const DEFAULT_MAX_BUFFER = 50;

// CCT-28 cat 3: ActivityTab used to open its own EventSource alongside any
// consumer of this hook (e.g. NarrationFeed), causing the daemon to receive
// two SSE subscriptions per page when the Activity tab was visible. The hook
// now accepts a `maxBuffer` knob so ActivityTab can use a single
// subscription without losing its larger backlog.
export function useNarrationStream(
  sessionFilter?: string,
  maxBuffer: number = DEFAULT_MAX_BUFFER,
) {
  const [events, setEvents] = useState<NarrationEvent[]>([]);

  useEffect(() => {
    const es = new EventSource("/api/narration-stream");
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as NarrationEvent;
        if (sessionFilter && ev.session_id !== sessionFilter) return;
        setEvents((prev) => {
          const next = prev.length >= maxBuffer ? prev.slice(prev.length - maxBuffer + 1) : prev.slice();
          next.push(ev);
          return next;
        });
      } catch {
        // ignore malformed events
      }
    };
    es.onerror = () => {
      // EventSource auto-reconnects; nothing to do here
    };
    return () => es.close();
  }, [sessionFilter, maxBuffer]);

  return events;
}
