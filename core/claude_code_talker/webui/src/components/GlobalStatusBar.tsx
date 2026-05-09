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
        <a
          href="/ui/"
          className="text-xs text-slate-500 hover:text-slate-300 underline"
          title="Open the legacy UI for advanced editing (voices, secrets, profiles, trigger tags)"
        >
          Advanced
        </a>
        <span className="text-xs text-slate-400 font-mono">
          {live} live session{live === 1 ? "" : "s"}
        </span>
      </div>
    </header>
  );
}
