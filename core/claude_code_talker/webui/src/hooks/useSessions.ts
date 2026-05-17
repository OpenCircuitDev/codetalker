import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useSessions() {
  // Phase 4 (2026-05-16): useDaemonEvents drives cache invalidation on
  // SessionChanged events (~50ms latency), so polling can drop from 5s
  // to 30s as a safety net for transient SSE drops (network blip, NAT
  // timeout). Phase 6 deletes refetchInterval entirely once SSE has
  // production soak time.
  //
  // keepPreviousData preserves the prior data reference across refetches
  // so memoized consumers (SessionGrid sort, React.memo'd cards) can
  // shallow-compare and skip re-renders.
  return useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    staleTime: 4000,
  });
}
