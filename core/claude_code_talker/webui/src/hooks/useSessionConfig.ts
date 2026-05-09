import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useSessionConfig(sessionId: string) {
  // CCT-28: keepPreviousData prevents the config object reference from
  // being briefly replaced during a background refetch, which was causing
  // controlled <select> popups (mute/mode/voice/cadence) inside
  // SessionControls to dismiss mid-edit on Windows.
  return useQuery({
    queryKey: ["session-config", sessionId],
    queryFn: () => api.sessionConfig(sessionId),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    enabled: Boolean(sessionId),
    placeholderData: keepPreviousData,
    staleTime: 4000,
  });
}
