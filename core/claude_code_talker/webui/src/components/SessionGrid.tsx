// Phase 27 — wrap session cards in AnimatePresence for entry/exit transitions.
import { AnimatePresence } from "framer-motion";
import { useSessions } from "../hooks/useSessions";
import { SessionCard } from "./SessionCard";

export function SessionGrid() {
  const { data, isLoading, error } = useSessions();

  if (isLoading) {
    return <div className="p-6 text-[var(--color-text-3)]">Loading sessions…</div>;
  }
  if (error) {
    return <div className="p-6 text-rose-400">Failed to load sessions</div>;
  }
  const live = (data ?? []).filter((s) => s.is_live);
  if (live.length === 0) {
    return (
      <div className="p-6 text-[var(--color-text-3)]">
        No live sessions right now.
      </div>
    );
  }
  const sorted = [...live].sort((a, b) => b.last_modified - a.last_modified);

  return (
    <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <AnimatePresence>
        {sorted.map((s) => (
          <SessionCard key={s.session_id} session={s} />
        ))}
      </AnimatePresence>
    </div>
  );
}
