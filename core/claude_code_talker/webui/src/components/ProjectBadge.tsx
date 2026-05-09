// CCT-28: ProjectBadge previously called Date.now() in the render path on
// every poll, so every visible card re-rendered its timestamp string each
// tick. We now memoize the relative-time string against `lastModified` plus
// a coarse 60s tick state — so within any minute the rendered string is
// identical, and the component is wrapped in React.memo to skip the work
// entirely when its inputs haven't changed.
import { memo, useEffect, useMemo, useState } from "react";

type Props = { slug: string; lastModified: number };

function relativeTime(epochSec: number, nowSec: number): string {
  const sec = Math.max(0, nowSec - epochSec);
  if (sec < 60) {
    const n = Math.floor(sec);
    return `${n} second${n === 1 ? "" : "s"} ago`;
  }
  if (sec < 3600) {
    const n = Math.floor(sec / 60);
    return `${n} minute${n === 1 ? "" : "s"} ago`;
  }
  if (sec < 86400) {
    const n = Math.floor(sec / 3600);
    return `${n} hour${n === 1 ? "" : "s"} ago`;
  }
  const n = Math.floor(sec / 86400);
  return `${n} day${n === 1 ? "" : "s"} ago`;
}

// One module-scoped 60s tick fans out to every ProjectBadge instance so we
// don't allocate a setInterval per card.
let tickListeners: Set<(t: number) => void> | null = null;
let tickHandle: ReturnType<typeof setInterval> | null = null;

function subscribeTick(listener: (t: number) => void): () => void {
  if (tickListeners === null) {
    tickListeners = new Set();
  }
  tickListeners.add(listener);
  if (tickHandle === null) {
    tickHandle = setInterval(() => {
      const now = Math.floor(Date.now() / 1000);
      tickListeners?.forEach((cb) => cb(now));
    }, 60_000);
  }
  return () => {
    tickListeners?.delete(listener);
    if (tickListeners && tickListeners.size === 0 && tickHandle !== null) {
      clearInterval(tickHandle);
      tickHandle = null;
    }
  };
}

function useCoarseNow(): number {
  const [now, setNow] = useState<number>(() => Math.floor(Date.now() / 1000));
  useEffect(() => subscribeTick(setNow), []);
  return now;
}

function ProjectBadgeImpl({ slug, lastModified }: Props) {
  const now = useCoarseNow();
  const rel = useMemo(() => relativeTime(lastModified, now), [lastModified, now]);
  return (
    <div className="flex flex-col text-xs">
      <span className="font-mono text-slate-300">{slug}</span>
      <span className="text-slate-500">{rel}</span>
    </div>
  );
}

export const ProjectBadge = memo(ProjectBadgeImpl);
