import { useDaemonHealth } from "../hooks/useDaemonHealth";
import { useSessions } from "../hooks/useSessions";

export function GlobalStatusBar() {
  const health = useDaemonHealth();
  const sessions = useSessions();
  const live = (sessions.data ?? []).filter((s) => s.is_live).length;
  const isHealthy = health.data?.ok === true;

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-950/60">
      <div className="flex items-center gap-3">
        <span className="text-lg font-semibold tracking-tight">codetalker</span>
        <span
          className={
            "h-2 w-2 rounded-full " +
            (isHealthy ? "bg-emerald-400" : "bg-rose-500")
          }
          title={isHealthy ? "daemon healthy" : "daemon unreachable"}
        />
      </div>
      <div className="flex items-center gap-4">
        {/* 2026-05-11 — Removed the "Advanced (legacy ↗)" link to /ui/
            after the legacy UI was retired (its top-level mute button
            kept causing accidental global mutes). The /ui route now
            302-redirects to /ui-react/, so the link would have been a
            no-op circle. Form-based controls migrating into the React
            UI itself when needed. */}
        <span className="text-xs text-slate-400 font-mono">
          {live} live session{live === 1 ? "" : "s"}
        </span>
      </div>
    </header>
  );
}
