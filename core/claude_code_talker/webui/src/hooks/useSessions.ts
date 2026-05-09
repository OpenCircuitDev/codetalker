import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useSessions() {
  return useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions,
    refetchInterval: 2000,
    refetchIntervalInBackground: false,
  });
}
