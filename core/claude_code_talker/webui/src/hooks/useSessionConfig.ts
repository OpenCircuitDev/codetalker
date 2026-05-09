import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useSessionConfig(sessionId: string) {
  return useQuery({
    queryKey: ["session-config", sessionId],
    queryFn: () => api.sessionConfig(sessionId),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    enabled: Boolean(sessionId),
  });
}
