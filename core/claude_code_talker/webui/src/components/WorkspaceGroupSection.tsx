// v0.1.0 unification — sticky group header with collapse/expand.
// Mirrors Pro Android SessionListScreen group rendering. Header reads
// `workspace_group` if set, else humanizes `project_dir` (last segment),
// else "Ungrouped".
import { useMemo } from "react";
import type { Session } from "../types";

type Props = {
  groupKey: string;
  sessions: Session[];
  collapsed: boolean;
  onToggle: () => void;
  /** Optional callback for the per-group settings icon. When omitted
   *  the icon is hidden. Mirrors the Claude.ai sidebar's per-group
   *  action affordance (the sliders icon next to "OCDev" etc.). */
  onSettings?: () => void;
  children: React.ReactNode;
};

export function WorkspaceGroupSection({
  groupKey,
  sessions,
  collapsed,
  onToggle,
  onSettings,
  children,
}: Props) {
  const liveCount = useMemo(() => sessions.filter((s) => s.is_live).length, [sessions]);
  const total = sessions.length;
  const isUngrouped = groupKey === "Ungrouped";

  return (
    <section
      className={
        "group/section " +
        (isUngrouped ? "border-t border-zinc-800/40 mt-2" : "")
      }
    >
      <header
        className={
          "sticky top-0 z-10 px-3 py-1.5 bg-[var(--color-surface-0,#0a0a0f)]/95 backdrop-blur-sm flex items-center gap-2 cursor-pointer select-none hover:bg-zinc-900/40 " +
          (isUngrouped ? "text-[var(--color-text-3)]" : "")
        }
        onClick={onToggle}
      >
        <span
          aria-hidden
          className={
            "inline-block transition-transform text-[10px] text-[var(--color-text-3)] " +
            (collapsed ? "" : "rotate-90")
          }
        >
          ▸
        </span>
        <h3
          className={
            "font-semibold text-xs uppercase tracking-wider truncate flex-1 " +
            (isUngrouped
              ? "text-[var(--color-text-3)]"
              : "text-[var(--color-text-2)]")
          }
        >
          {groupKey}
        </h3>
        <span className="text-[10px] text-[var(--color-text-3)] font-mono shrink-0">
          {liveCount}/{total}
        </span>
        {onSettings && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onSettings();
            }}
            className="opacity-0 group-hover/section:opacity-60 hover:opacity-100 transition-opacity p-0.5 text-[var(--color-text-3)]"
            title={`Settings for ${groupKey}`}
            aria-label={`Settings for ${groupKey}`}
          >
            <SlidersIcon />
          </button>
        )}
      </header>
      {!collapsed && <div className="px-2 py-1 space-y-1.5">{children}</div>}
    </section>
  );
}

function SlidersIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
      <circle cx="9" cy="6" r="2" fill="currentColor" />
      <circle cx="15" cy="12" r="2" fill="currentColor" />
      <circle cx="9" cy="18" r="2" fill="currentColor" />
    </svg>
  );
}

/** Generic tails that don't make great standalone group labels — when
 *  a project_dir ends with one of these, include the prior segment for
 *  context. Mirrors the Android SessionListScreen heuristic so both
 *  surfaces produce the same group label per session.
 *  Source of truth: companion-android/.../ui/SessionListScreen.kt
 *                   :humanizeProjectDir. */
const GENERIC_TAILS = new Set([
  "Workbench", "Workspace", "Web", "Clean", "Forge", "Dev",
  "App", "Server", "Client", "Repo", "src", "project",
]);

/** Humanize Claude Code's encoded project_dir name into a workspace label.
 *  Claude Code stores transcripts under `~/.claude/projects/<encoded-cwd>/`
 *  where the encoded form replaces path separators with `-`, producing
 *  names like "C--Users-brand-Dropbox-OCR-Open-Circuit-codetalker".
 *  We strip the leading drive letter ("C" or "c"), then take the trailing
 *  1–2 segments, preferring 2 when the last segment is a generic tail. */
export function humanizeProjectDir(dir: string): string {
  const parts = dir
    .split("-")
    .filter((p) => p.length > 0 && p !== "C" && p !== "c");
  if (parts.length === 0) return dir;
  const last = parts[parts.length - 1];
  if (parts.length >= 2 && GENERIC_TAILS.has(last)) {
    return parts.slice(-2).join(" / ");
  }
  return last;
}

/** Resolve a session's group label. Priority order matches the Android
 *  SessionListScreen.workspaceLabel() — both surfaces produce identical
 *  group labels for the same session so cross-surface parity holds:
 *    1. workspace_group (user-set override)
 *    2. humanized project_dir (Claude Code's project folder name)
 *    3. cwd leaf (live sessions whose catalog scan hasn't run yet)
 *    4. project_slug (codetalker's older derived name)
 *    5. "Ungrouped" */
export function groupLabelFor(s: Session): string {
  if (s.workspace_group && s.workspace_group.trim()) return s.workspace_group;
  if (s.project_dir && s.project_dir.trim()) {
    return humanizeProjectDir(s.project_dir);
  }
  const cwd = s.cwd ?? "";
  if (cwd.trim()) {
    const seg = cwd.replace(/\\/g, "/").split("/").filter(Boolean).pop();
    if (seg) return seg;
  }
  // project_slug isn't on the Session type yet but the wire response has it.
  const slug = (s as unknown as { project_slug?: string }).project_slug;
  if (slug && slug.trim()) return slug;
  return "Ungrouped";
}

/** Group sessions by their resolved label, preserving order.
 *
 *  v0.1.0 unification — dedupe is **case-insensitive**. Without this,
 *  `workspace_group="CodeTalker"` (user-set, mixed case) and the
 *  `humanizeProjectDir("...-codetalker")="codetalker"` fallback would
 *  show as two separate groups in the sidebar even though they're
 *  semantically the same. The first-seen casing wins as the display
 *  form so the user sees their own capitalization preserved when set.
 */
export function groupSessions(sessions: Session[]): Map<string, Session[]> {
  const groups = new Map<string, Session[]>();
  // Track lowercased label -> canonical display form so we can merge
  // case-variant duplicates.
  const canonical = new Map<string, string>();
  for (const s of sessions) {
    const raw = groupLabelFor(s);
    const key = raw.toLowerCase();
    let display = canonical.get(key);
    if (!display) {
      display = raw;
      canonical.set(key, display);
    }
    const arr = groups.get(display);
    if (arr) arr.push(s);
    else groups.set(display, [s]);
  }
  return groups;
}
