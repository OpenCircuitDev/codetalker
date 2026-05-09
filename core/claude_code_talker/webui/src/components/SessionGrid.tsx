import { useSessions } from "../hooks/useSessions";
import { SessionCard } from "./SessionCard";

export function SessionGrid() {
  const { data, isLoading, error } = useSessions();

  if (isLoading) {
    return <div className="p-6 text-slate-500">Loading sessions…</div>;
  }
  if (error) {
    return <div className="p-6 text-rose-400">Failed to load sessions</div>;
  }
  const live = (data ?? []).filter((s) => s.is_live);
  if (live.length === 0) {
    return <div className="p-6 text-slate-500">No live sessions right now.</div>;
  }
  const sorted = [...live].sort((a, b) => b.last_modified - a.last_modified);

  return (
    <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {sorted.map((s) => (
        <SessionCard key={s.session_id} session={s} />
      ))}
    </div>
  );
}
