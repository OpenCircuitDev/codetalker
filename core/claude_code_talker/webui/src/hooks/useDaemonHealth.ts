import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useDaemonHealth() {
  // Phase 4 — useDaemonEvents invalidates this query on
  // MasterConfigChanged events (the narration_enabled field flips with
  // the master toggle). 30s polling stays as a safety net for the
  // narration_warning string and unrelated health-blob updates.
  return useQuery({
    queryKey: ["daemon-health"],
    queryFn: api.health,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
