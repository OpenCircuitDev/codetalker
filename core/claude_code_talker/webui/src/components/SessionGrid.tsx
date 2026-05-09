// Phase 27 — wrap session cards in AnimatePresence for entry/exit transitions.
import { useMemo } from "react";
import { AnimatePresence } from "framer-motion";
import { useSessions } from "../hooks/useSessions";
import { SessionCard } from "./SessionCard";
import type { Session } from "../types";

export function SessionGrid() {
  const { data, isLoading, error } = useSessions();

  // CCT-28: memoize the sorted list so the array identity is stable when
  // useSessions returns reference-equal data via keepPreviousData. Without
  // this, the inline `[...live].sort(...)` produced a fresh array on every
  // render — defeating React.memo on SessionCard and triggering
  // AnimatePresence layout reflow that was dismissing open <select> popups.
  const sorted = useMemo<Session[]>(() => {
    const live = (data ?? []).filter((s) => s.is_live);
    return [...live].sort((a, b) => b.last_modified - a.last_modified);
  }, [data]);

  if (isLoading) {
    return <div className="p-6 text-[var(--color-text-3)]">Loading sessions…</div>;
  }
  if (error) {
    return <div className="p-6 text-rose-400">Failed to load sessions</div>;
  }
  if (sorted.length === 0) {
    return (
      <div className="p-6 text-[var(--color-text-3)]">
        No live sessions right now.
      </div>
    );
  }

  return (
    <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <AnimatePresence mode="popLayout">
        {sorted.map((s) => (
          <SessionCard key={s.session_id} session={s} />
        ))}
      </AnimatePresence>
    </div>
  );
}
