import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useSessions() {
  // CCT-28: keepPreviousData preserves the prior data reference across
  // refetches so memoized consumers (SessionGrid sort, React.memo'd cards)
  // can shallow-compare and skip re-renders. Polling is bumped to 5s — the
  // narration SSE stream already pushes hot deltas, so 2s polling was
  // mostly wasted churn.
  return useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    staleTime: 4000,
  });
}
