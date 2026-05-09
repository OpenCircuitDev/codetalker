import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useDaemonHealth() {
  return useQuery({
    queryKey: ["daemon-health"],
    queryFn: api.health,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
