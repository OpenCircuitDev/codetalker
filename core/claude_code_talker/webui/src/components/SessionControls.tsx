import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { ModePicker } from "./ModePicker";
import { VoicePicker } from "./VoicePicker";
import { CadencePicker } from "./CadencePicker";
import type { SessionConfig } from "../types";

type Props = {
  sessionId: string;
  config: SessionConfig | undefined;
};

export function SessionControls({ sessionId, config }: Props) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: (overlay: Partial<SessionConfig>) => api.putOverlay(sessionId, overlay),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["session-config", sessionId] }),
  });

  const muted = config?.enabled === false;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        className={
          "text-xs px-2 py-1 rounded font-mono border " +
          (muted
            ? "bg-rose-900/40 text-rose-200 border-rose-700"
            : "bg-slate-900 text-slate-200 border-slate-700 hover:bg-slate-800")
        }
        onClick={() => mutation.mutate({ enabled: muted })}
        disabled={mutation.isPending}
      >
        {muted ? "unmute" : "mute"}
      </button>
      <ModePicker
        value={config?.active_mode}
        onChange={(active_mode) => mutation.mutate({ active_mode })}
      />
      <VoicePicker
        value={config?.voice?.model}
        onChange={(model) => mutation.mutate({ voice: { ...config?.voice, model } })}
      />
      {/* CCT-28 cat 4 — cadence applies only to live mode, but is shown
          alongside mode/voice for parity with the legacy panel. The
          backend ignores cadence overlays when active_mode != "live". */}
      <CadencePicker
        value={config?.live?.cadence}
        onChange={(cadence) =>
          mutation.mutate({ live: { ...config?.live, cadence } })
        }
      />
      {/* Markup quick controls now live in SessionMarkupQuick (inline, per-session). */}
    </div>
  );
}
