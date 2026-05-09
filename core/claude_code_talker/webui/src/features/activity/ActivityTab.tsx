// Phase 27 — global activity log (filled in Task 9).
import { LiveTicker } from "../../components/LiveTicker";

export function ActivityTab() {
  return (
    <div className="h-full p-4">
      <LiveTicker events={[]} />
    </div>
  );
}
