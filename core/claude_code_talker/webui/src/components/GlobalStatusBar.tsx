import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDaemonHealth } from "../hooks/useDaemonHealth";
import { useSessions } from "../hooks/useSessions";
import { api } from "../api/client";

export function GlobalStatusBar() {
  const health = useDaemonHealth();
  const sessions = useSessions();
  const live = (sessions.data ?? []).filter((s) => s.is_live).length;
  const isHealthy = health.data?.ok === true;

  // 2026-05-16 -- master narration switch. Mirrors the Pro Android
  // Preferences toggle: a single tap mutes the entire fleet without
  // diving into per-session settings. Backed by tts_config.yaml so the
  // change persists across daemon restart. Optimistic update for snappy
  // UX; on error we re-fetch the daemon truth.
  const qc = useQueryClient();
  const master = useQuery({
    queryKey: ["master-enabled"],
    queryFn: api.masterEnabled,
    // Phase 4 — useDaemonEvents invalidates this on
    // MasterConfigChanged events; polling is a safety net.
    refetchInterval: 30000,
    retry: false,
  });
  const masterMutation = useMutation({
    mutationFn: api.setMasterEnabled,
    onMutate: async (newValue) => {
      await qc.cancelQueries({ queryKey: ["master-enabled"] });
      const previous = qc.getQueryData<{ enabled: boolean }>(["master-enabled"]);
      qc.setQueryData(["master-enabled"], { enabled: newValue });
      return { previous };
    },
    onError: (_e, _newValue, ctx) => {
      if (ctx?.previous) qc.setQueryData(["master-enabled"], ctx.previous);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["master-enabled"] });
      qc.invalidateQueries({ queryKey: ["daemon-health"] });
    },
  });
  const masterEnabled = master.data?.enabled ?? true;

  // Rewind last 30 seconds button — re-narrates the last N seconds of the log
  const rewindMutation = useMutation({
    mutationFn: () => api.audioRewind(30),
    onSuccess: () => {
      // Show success feedback briefly; no toast needed for this low-friction action
    },
    onError: () => {
      // Silently fail on error; the button remains clickable
    },
  });

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
        {/* Master narration toggle -- one tap silences the fleet. */}
        <button
          type="button"
          onClick={() => masterMutation.mutate(!masterEnabled)}
          disabled={masterMutation.isPending || master.isLoading}
          className={
            "px-3 py-1 rounded-full text-xs font-medium transition-colors border " +
            (masterEnabled
              ? "bg-emerald-900/40 text-emerald-200 border-emerald-700 hover:bg-emerald-900/60"
              : "bg-amber-900/40 text-amber-200 border-amber-700 hover:bg-amber-900/60")
          }
          title={
            masterEnabled
              ? "Narration ON for all sessions. Click to silence the fleet."
              : "Narration OFF for all sessions (~/.claude/scripts/tts_config.yaml enabled: false). Click to re-enable."
          }
        >
          {masterEnabled ? "🔊 Narration ON" : "🔇 Narration OFF"}
        </button>
        {/* Rewind last 30 seconds button */}
        <button
          type="button"
          onClick={() => rewindMutation.mutate()}
          disabled={rewindMutation.isPending}
          className="px-3 py-1 rounded-full text-xs font-medium transition-colors border bg-slate-800/40 text-slate-200 border-slate-600 hover:bg-slate-700/60 disabled:opacity-50 disabled:cursor-not-allowed"
          title="Re-play the last 30 seconds of narration (useful when you missed something)"
        >
          {rewindMutation.isPending ? "Rewinding…" : "⏮ Rewind 30s"}
        </button>
        <span className="text-xs text-slate-400 font-mono">
          {live} live session{live === 1 ? "" : "s"}
        </span>
      </div>
    </header>
  );
}
