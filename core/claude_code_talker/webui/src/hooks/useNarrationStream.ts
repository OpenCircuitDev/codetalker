import { useEffect, useState } from "react";
import type { NarrationEvent } from "../types";

const MAX_BUFFER = 50;

export function useNarrationStream(sessionFilter?: string) {
  const [events, setEvents] = useState<NarrationEvent[]>([]);

  useEffect(() => {
    const es = new EventSource("/api/narration-stream");
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as NarrationEvent;
        if (sessionFilter && ev.session_id !== sessionFilter) return;
        setEvents((prev) => {
          const next = [...prev, ev];
          if (next.length > MAX_BUFFER) next.shift();
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
  }, [sessionFilter]);

  return events;
}
