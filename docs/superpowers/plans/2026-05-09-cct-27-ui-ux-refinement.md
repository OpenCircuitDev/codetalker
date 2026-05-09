# CCT Phase 27 — UI/UX Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the React dashboard around three pillars: a layered, calm visual surface; live narration ticker as the heartbeat; and Characters as first-class identity. Result: SessionCard four-zone redesign, resizable narration panel, framer-motion entry/exit, top tab nav, sound-effects preference (off-by-default).

**Architecture:** Token-driven CSS via Tailwind v4 `@theme` block (surface palette + accent colors). New `LiveTicker.tsx` consumes existing SSE event stream and exposes a filter ribbon. SessionCard becomes 4 zones: identity, chips, live ticker, controls. `framer-motion` drives entry/exit and "speaking" breathing animation. New top-level tab nav (Sessions | Characters | Markup | Activity) replaces ad-hoc nav. PreferencesPanel includes sound effects toggle backed by localStorage.

**Tech Stack:** React 19, Tailwind v4, framer-motion (already on package.json), react-resizable-panels (already on package.json), TypeScript, Vite 6.

**Reference spec:** [docs/superpowers/specs/2026-05-09-cct-27-ui-ux-refinement-design.md](../specs/2026-05-09-cct-27-ui-ux-refinement-design.md) — read before starting.

**File structure**:
```
core/claude_code_talker/webui/src/
├── theme/
│   ├── tokens.css                       # NEW — surface + accent CSS custom props
│   └── motion.ts                        # NEW — shared variants for framer-motion
├── components/
│   ├── DashboardShell.tsx               # MODIFY — top tab nav + tabs
│   ├── PreferencesPanel.tsx             # NEW — sound effects, density, accent
│   ├── SessionCard.tsx                  # REWRITE — 4-zone layout
│   ├── LiveTicker.tsx                   # NEW — filterable feed of SSE events
│   ├── SpeakingDot.tsx                  # NEW — breathing animation indicator
│   └── CharacterAvatar.tsx              # NEW — emerging-on-attach avatar
├── hooks/
│   ├── useSse.ts                        # MAYBE EXTRACT — already may exist
│   └── usePreferences.ts                # NEW — localStorage-backed prefs
├── features/
│   └── activity/
│       └── ActivityTab.tsx              # NEW — global activity log (read-only)

core/claude_code_talker/webui/src/__tests__/
├── SessionCard.test.tsx                 # NEW — 4 tests
├── LiveTicker.test.tsx                  # NEW — 4 tests
├── PreferencesPanel.test.tsx            # NEW — 3 tests
└── usePreferences.test.tsx              # NEW — 3 tests
```

---

## Task 1: Theme tokens + motion variants

**Files:**
- Create: `core/claude_code_talker/webui/src/theme/tokens.css`
- Create: `core/claude_code_talker/webui/src/theme/motion.ts`
- Modify: `core/claude_code_talker/webui/src/index.css` (or main entry CSS)

- [ ] **Step 1: Write tokens.css**

```css
@theme {
  --color-surface-0: #0a0b10;
  --color-surface-1: #11141c;
  --color-surface-2: #171b26;
  --color-surface-3: #1f2533;
  --color-text-1: #e6e8ee;
  --color-text-2: #aab1c0;
  --color-text-3: #6e7585;
  --color-accent-live: #34d399;
  --color-accent-muted: #fb7185;
  --color-accent-activity: #a78bfa;
  --color-accent-brand: #22d3ee;
  --color-accent-warn: #fbbf24;
  --shadow-soft-1: 0 4px 12px -4px rgba(0, 0, 0, 0.3);
  --shadow-soft-2: 0 8px 28px -8px rgba(0, 0, 0, 0.4);
}

body {
  background: var(--color-surface-0);
  color: var(--color-text-1);
}
```

- [ ] **Step 2: Import in index.css (or main.tsx)**

In `core/claude_code_talker/webui/src/index.css`, add at top:

```css
@import "./theme/tokens.css";
```

- [ ] **Step 3: Write motion.ts**

```typescript
import type { Variants } from "framer-motion";

export const cardEntry: Variants = {
  initial: { opacity: 0, y: 8, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.22, ease: "easeOut" } },
  exit: { opacity: 0, y: -4, scale: 0.97, transition: { duration: 0.16 } },
};

export const breathing: Variants = {
  idle: { scale: 1 },
  speaking: {
    scale: [1, 1.06, 1],
    transition: { duration: 1.6, repeat: Infinity, ease: "easeInOut" },
  },
};

export const tickerEntry: Variants = {
  initial: { opacity: 0, x: -8 },
  animate: { opacity: 1, x: 0, transition: { duration: 0.18 } },
  exit: { opacity: 0, x: 4, transition: { duration: 0.12 } },
};

export const avatarEmerge: Variants = {
  initial: { scale: 0.4, opacity: 0, rotate: -8 },
  animate: { scale: 1, opacity: 1, rotate: 0, transition: { type: "spring", stiffness: 300, damping: 22 } },
};
```

- [ ] **Step 4: Build verifies**

Run: `cd core/claude_code_talker/webui && npm run build`

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/webui/src/theme/ core/claude_code_talker/webui/src/index.css
git commit -m "feat(theme): surface palette tokens + motion variants (Phase 27 Task 1)"
```

---

## Task 2: usePreferences hook (TDD)

**Files:**
- Create: `core/claude_code_talker/webui/src/hooks/usePreferences.ts`
- Create: `core/claude_code_talker/webui/src/__tests__/usePreferences.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePreferences } from "../hooks/usePreferences";

describe("usePreferences", () => {
  beforeEach(() => localStorage.clear());

  it("defaults sound effects off", () => {
    const { result } = renderHook(() => usePreferences());
    expect(result.current.prefs.soundEffects).toBe(false);
  });

  it("persists changes to localStorage", () => {
    const { result } = renderHook(() => usePreferences());
    act(() => result.current.setPref("soundEffects", true));
    const raw = localStorage.getItem("cct.prefs");
    expect(raw).toContain("\"soundEffects\":true");
  });

  it("loads persisted prefs on mount", () => {
    localStorage.setItem("cct.prefs", JSON.stringify({ soundEffects: true, density: "compact" }));
    const { result } = renderHook(() => usePreferences());
    expect(result.current.prefs.soundEffects).toBe(true);
    expect(result.current.prefs.density).toBe("compact");
  });
});
```

- [ ] **Step 2: Implement hook**

```typescript
import { useCallback, useEffect, useState } from "react";

export interface Preferences {
  soundEffects: boolean;
  density: "compact" | "comfortable";
  accent: "cyan" | "emerald" | "violet";
}

const KEY = "cct.prefs";
const DEFAULTS: Preferences = { soundEffects: false, density: "comfortable", accent: "cyan" };

function load(): Preferences {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return DEFAULTS;
  }
}

export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(() => load());

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch {}
  }, [prefs]);

  const setPref = useCallback(<K extends keyof Preferences>(k: K, v: Preferences[K]) => {
    setPrefs((p) => ({ ...p, [k]: v }));
  }, []);

  return { prefs, setPref };
}
```

- [ ] **Step 3: Tests pass**

Run: `cd core/claude_code_talker/webui && npx vitest run usePreferences`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/hooks/usePreferences.ts core/claude_code_talker/webui/src/__tests__/usePreferences.test.tsx
git commit -m "feat(webui): usePreferences hook with localStorage persistence (Phase 27 Task 2)"
```

---

## Task 3: PreferencesPanel component (TDD)

**Files:**
- Create: `core/claude_code_talker/webui/src/components/PreferencesPanel.tsx`
- Create: `core/claude_code_talker/webui/src/__tests__/PreferencesPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PreferencesPanel } from "../components/PreferencesPanel";

describe("PreferencesPanel", () => {
  beforeEach(() => localStorage.clear());

  it("renders sound effects toggle off by default", () => {
    render(<PreferencesPanel />);
    const toggle = screen.getByLabelText(/sound effects/i) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
  });

  it("toggling sound effects persists", () => {
    render(<PreferencesPanel />);
    const toggle = screen.getByLabelText(/sound effects/i);
    fireEvent.click(toggle);
    expect(localStorage.getItem("cct.prefs")).toContain("\"soundEffects\":true");
  });

  it("density radio updates pref", () => {
    render(<PreferencesPanel />);
    fireEvent.click(screen.getByLabelText(/compact/i));
    expect(localStorage.getItem("cct.prefs")).toContain("\"density\":\"compact\"");
  });
});
```

- [ ] **Step 2: Implement**

```tsx
import { usePreferences } from "../hooks/usePreferences";

export function PreferencesPanel() {
  const { prefs, setPref } = usePreferences();
  return (
    <section className="space-y-4 p-4 bg-[var(--color-surface-1)] rounded-lg border border-zinc-800">
      <h2 className="font-bold">Preferences</h2>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={prefs.soundEffects}
          onChange={(e) => setPref("soundEffects", e.target.checked)}
        />
        <span>Sound effects</span>
        <span className="text-xs text-zinc-500">(off by default)</span>
      </label>
      <fieldset className="space-y-1">
        <legend className="text-sm text-zinc-400">Density</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name="density" checked={prefs.density === "comfortable"} onChange={() => setPref("density", "comfortable")} />
          <span>Comfortable</span>
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="density" checked={prefs.density === "compact"} onChange={() => setPref("density", "compact")} />
          <span>Compact</span>
        </label>
      </fieldset>
    </section>
  );
}
```

- [ ] **Step 3: Tests pass**

Run: `cd core/claude_code_talker/webui && npx vitest run PreferencesPanel`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/components/PreferencesPanel.tsx core/claude_code_talker/webui/src/__tests__/PreferencesPanel.test.tsx
git commit -m "feat(webui): PreferencesPanel with sound effects + density (Phase 27 Task 3)"
```

---

## Task 4: SpeakingDot — breathing indicator

**Files:**
- Create: `core/claude_code_talker/webui/src/components/SpeakingDot.tsx`

- [ ] **Step 1: Implement**

```tsx
import { motion } from "framer-motion";
import { breathing } from "../theme/motion";

export function SpeakingDot({ active }: { active: boolean }) {
  return (
    <motion.span
      aria-hidden
      variants={breathing}
      animate={active ? "speaking" : "idle"}
      className={`inline-block w-2.5 h-2.5 rounded-full ${active ? "bg-[var(--color-accent-live)]" : "bg-zinc-600"}`}
    />
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/webui/src/components/SpeakingDot.tsx
git commit -m "feat(webui): SpeakingDot breathing indicator (Phase 27 Task 4)"
```

---

## Task 5: CharacterAvatar — emerging-on-attach

**Files:**
- Create: `core/claude_code_talker/webui/src/components/CharacterAvatar.tsx`

- [ ] **Step 1: Implement**

```tsx
import { motion } from "framer-motion";
import { avatarEmerge } from "../theme/motion";

interface Props {
  name: string;
  meshUrl?: string | null;
  persona?: string | null;
  size?: "sm" | "md" | "lg";
}

const PERSONA_GRADIENTS: Record<string, string> = {
  methodical: "from-slate-700 to-slate-900",
  warm: "from-amber-600 to-rose-800",
  technical: "from-cyan-600 to-blue-900",
  plain: "from-zinc-600 to-zinc-800",
  sarcastic: "from-fuchsia-600 to-purple-900",
  energetic: "from-rose-500 to-orange-700",
};

const SIZES = { sm: "w-8 h-8 text-xs", md: "w-12 h-12 text-base", lg: "w-20 h-20 text-2xl" };

export function CharacterAvatar({ name, meshUrl, persona, size = "md" }: Props) {
  const initial = name.trim()[0]?.toUpperCase() || "?";
  const gradient = PERSONA_GRADIENTS[persona || ""] || "from-zinc-600 to-zinc-800";
  return (
    <motion.div
      variants={avatarEmerge}
      initial="initial"
      animate="animate"
      className={`${SIZES[size]} rounded-full bg-gradient-to-br ${gradient} flex items-center justify-center font-bold text-white shadow-md`}
      title={name}
    >
      {meshUrl ? (
        <img src={meshUrl} alt={name} className="rounded-full w-full h-full object-cover" />
      ) : (
        initial
      )}
    </motion.div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/webui/src/components/CharacterAvatar.tsx
git commit -m "feat(webui): CharacterAvatar with persona gradient + spring entry (Phase 27 Task 5)"
```

---

## Task 6: LiveTicker (TDD)

**Files:**
- Create: `core/claude_code_talker/webui/src/components/LiveTicker.tsx`
- Create: `core/claude_code_talker/webui/src/__tests__/LiveTicker.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LiveTicker } from "../components/LiveTicker";

const events = [
  { id: "1", kind: "speak", text: "Hello there", ts: 1234 },
  { id: "2", kind: "tool", text: "Bash succeeded", ts: 1235 },
  { id: "3", kind: "speak", text: "Phase complete", ts: 1236 },
];

describe("LiveTicker", () => {
  it("renders all events when no filter", () => {
    render(<LiveTicker events={events} />);
    expect(screen.getByText(/hello there/i)).toBeInTheDocument();
    expect(screen.getByText(/bash succeeded/i)).toBeInTheDocument();
  });

  it("filters to only speak events", () => {
    render(<LiveTicker events={events} />);
    fireEvent.click(screen.getByRole("button", { name: /speak/i }));
    expect(screen.queryByText(/bash succeeded/i)).not.toBeInTheDocument();
    expect(screen.getByText(/hello there/i)).toBeInTheDocument();
  });

  it("shows empty state when no events", () => {
    render(<LiveTicker events={[]} />);
    expect(screen.getByText(/quiet/i)).toBeInTheDocument();
  });

  it("scrolls to most recent on update", () => {
    const { rerender } = render(<LiveTicker events={events} />);
    rerender(<LiveTicker events={[...events, { id: "4", kind: "speak", text: "Latest", ts: 1237 }]} />);
    expect(screen.getByText("Latest")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { tickerEntry } from "../theme/motion";

export interface TickerEvent {
  id: string;
  kind: string;       // "speak" | "tool" | "system" | "error" | "subagent"
  text: string;
  ts: number;
}

const FILTER_OPTIONS = [
  { kind: "all", label: "All", color: "bg-zinc-700" },
  { kind: "speak", label: "Speak", color: "bg-emerald-700" },
  { kind: "tool", label: "Tool", color: "bg-cyan-700" },
  { kind: "subagent", label: "Subagent", color: "bg-violet-700" },
  { kind: "error", label: "Error", color: "bg-rose-700" },
];

export function LiveTicker({ events, maxEvents = 100 }: { events: TickerEvent[]; maxEvents?: number }) {
  const [filter, setFilter] = useState("all");
  const filtered = useMemo(() => {
    const list = filter === "all" ? events : events.filter((e) => e.kind === filter);
    return list.slice(-maxEvents);
  }, [events, filter, maxEvents]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 p-2 border-b border-zinc-800">
        {FILTER_OPTIONS.map((o) => (
          <button
            key={o.kind}
            onClick={() => setFilter(o.kind)}
            className={`px-2 py-0.5 rounded text-xs ${filter === o.kind ? o.color + " text-white" : "bg-zinc-800 text-zinc-400"}`}
          >
            {o.label}
          </button>
        ))}
      </div>
      <ul className="flex-1 overflow-y-auto p-2 space-y-1">
        {filtered.length === 0 && <li className="text-zinc-500 italic text-sm">It's quiet. Waiting for activity…</li>}
        <AnimatePresence initial={false}>
          {filtered.map((e) => (
            <motion.li
              key={e.id}
              variants={tickerEntry}
              initial="initial"
              animate="animate"
              exit="exit"
              className="text-sm p-1 rounded bg-[var(--color-surface-2)] flex gap-2"
            >
              <span className={`inline-block px-1.5 rounded text-xs uppercase ${kindBg(e.kind)}`}>{e.kind}</span>
              <span className="flex-1">{e.text}</span>
              <span className="text-zinc-500 text-xs">{new Date(e.ts).toLocaleTimeString().slice(0, 8)}</span>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}

function kindBg(kind: string): string {
  switch (kind) {
    case "speak": return "bg-emerald-700 text-emerald-100";
    case "tool": return "bg-cyan-700 text-cyan-100";
    case "subagent": return "bg-violet-700 text-violet-100";
    case "error": return "bg-rose-700 text-rose-100";
    default: return "bg-zinc-700 text-zinc-100";
  }
}
```

- [ ] **Step 3: Tests pass**

Run: `cd core/claude_code_talker/webui && npx vitest run LiveTicker`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/components/LiveTicker.tsx core/claude_code_talker/webui/src/__tests__/LiveTicker.test.tsx
git commit -m "feat(webui): LiveTicker with filter ribbon + framer-motion (Phase 27 Task 6)"
```

---

## Task 7: SessionCard 4-zone rewrite (TDD)

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/SessionCard.tsx`
- Create: `core/claude_code_talker/webui/src/__tests__/SessionCard.test.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionCard } from "../components/SessionCard";

const session = {
  session_id: "abc123",
  title: "fix auth bug",
  cwd: "/repos/myapp",
  attached_character: { id: "robin", display_name: "Robin", persona: "warm", voice_ref: "char-robin" },
  is_speaking: true,
  events: [{ id: "1", kind: "speak", text: "Working", ts: Date.now() }],
} as any;

describe("SessionCard", () => {
  it("renders identity zone with title and cwd", () => {
    render(<SessionCard session={session} />);
    expect(screen.getByText(/fix auth bug/i)).toBeInTheDocument();
    expect(screen.getByText(/myapp/i)).toBeInTheDocument();
  });

  it("renders character avatar when attached", () => {
    render(<SessionCard session={session} />);
    expect(screen.getByTitle("Robin")).toBeInTheDocument();
  });

  it("speaking dot is active when is_speaking=true", () => {
    const { container } = render(<SessionCard session={session} />);
    const dot = container.querySelector(".bg-emerald-400, [class*='accent-live']");
    expect(dot).toBeTruthy();
  });

  it("renders ticker when events present", () => {
    render(<SessionCard session={session} />);
    expect(screen.getByText("Working")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rewrite SessionCard**

```tsx
import { motion } from "framer-motion";
import { cardEntry } from "../theme/motion";
import { CharacterAvatar } from "./CharacterAvatar";
import { LiveTicker } from "./LiveTicker";
import { SpeakingDot } from "./SpeakingDot";

interface Session {
  session_id: string;
  title?: string | null;
  cwd?: string | null;
  attached_character?: any;
  is_speaking?: boolean;
  is_muted?: boolean;
  mode?: string;
  events?: any[];
}

export function SessionCard({ session }: { session: Session }) {
  const char = session.attached_character;
  return (
    <motion.article
      variants={cardEntry}
      initial="initial"
      animate="animate"
      exit="exit"
      className="bg-[var(--color-surface-1)] border border-zinc-800 rounded-lg p-3 space-y-2 shadow-soft-1"
    >
      {/* Zone 1: identity */}
      <header className="flex items-center gap-3">
        {char ? (
          <CharacterAvatar name={char.display_name} meshUrl={char.mesh_path} persona={char.persona} size="md" />
        ) : (
          <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center text-xs text-zinc-500">no char</div>
        )}
        <div className="flex-1 min-w-0">
          <h3 className="font-bold truncate">{session.title || session.session_id.slice(0, 8)}</h3>
          <p className="text-xs text-zinc-500 truncate">{session.cwd || "—"}</p>
        </div>
        <SpeakingDot active={!!session.is_speaking} />
      </header>

      {/* Zone 2: chips */}
      <div className="flex items-center gap-2 text-xs flex-wrap">
        {session.mode && <span className="px-2 py-0.5 rounded bg-zinc-800">{session.mode}</span>}
        {session.is_muted && <span className="px-2 py-0.5 rounded bg-rose-900 text-rose-200">muted</span>}
        {char && <span className="px-2 py-0.5 rounded bg-cyan-900 text-cyan-200">{char.display_name}</span>}
      </div>

      {/* Zone 3: live ticker */}
      <div className="h-32 bg-[var(--color-surface-2)] rounded">
        <LiveTicker events={session.events || []} maxEvents={20} />
      </div>

      {/* Zone 4: controls */}
      <footer className="flex items-center gap-2 text-sm">
        <button className="px-2 py-1 bg-zinc-800 rounded hover:bg-zinc-700">Mute</button>
        <button className="px-2 py-1 bg-zinc-800 rounded hover:bg-zinc-700">Mode</button>
        <button className="px-2 py-1 bg-zinc-800 rounded hover:bg-zinc-700">Detach</button>
      </footer>
    </motion.article>
  );
}
```

- [ ] **Step 3: Tests pass**

Run: `cd core/claude_code_talker/webui && npx vitest run SessionCard`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/components/SessionCard.tsx core/claude_code_talker/webui/src/__tests__/SessionCard.test.tsx
git commit -m "feat(webui): SessionCard 4-zone redesign (Phase 27 Task 7)"
```

---

## Task 8: Top tab nav in DashboardShell

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/DashboardShell.tsx`

- [ ] **Step 1: Add top tab nav**

```tsx
import { useState } from "react";
import { CharactersTab } from "../features/characters/CharactersTab";
import { ActivityTab } from "../features/activity/ActivityTab";
import { PreferencesPanel } from "./PreferencesPanel";
// existing SessionsTab

const TABS = [
  { id: "sessions", label: "Sessions" },
  { id: "characters", label: "Characters" },
  { id: "markup", label: "Markup", external: "/ui/#markup" },
  { id: "activity", label: "Activity" },
  { id: "preferences", label: "Preferences" },
] as const;

export function DashboardShell() {
  const [tab, setTab] = useState("sessions");

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-surface-0)]">
      <nav className="flex gap-1 p-2 border-b border-zinc-800 bg-[var(--color-surface-1)]">
        {TABS.map((t) => (
          t.external ? (
            <a key={t.id} href={t.external} target="_blank" rel="noopener" className="px-3 py-1 rounded text-zinc-400 hover:bg-zinc-800">
              {t.label} ↗
            </a>
          ) : (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1 rounded ${tab === t.id ? "bg-cyan-700 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}
            >
              {t.label}
            </button>
          )
        ))}
      </nav>
      <main className="flex-1 p-4 overflow-hidden">
        {tab === "sessions" && <SessionsPane />}
        {tab === "characters" && <CharactersTab />}
        {tab === "activity" && <ActivityTab />}
        {tab === "preferences" && <PreferencesPanel />}
      </main>
    </div>
  );
}
```

(Wire `SessionsPane` to whatever existing component owns the sessions list — keep its structure.)

- [ ] **Step 2: Build verifies**

Run: `cd core/claude_code_talker/webui && npm run build`

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/components/DashboardShell.tsx
git commit -m "feat(webui): top tab nav with sessions/characters/markup/activity/preferences (Phase 27 Task 8)"
```

---

## Task 9: ActivityTab — global activity log

**Files:**
- Create: `core/claude_code_talker/webui/src/features/activity/ActivityTab.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useEffect, useState } from "react";
import { LiveTicker, type TickerEvent } from "../../components/LiveTicker";

export function ActivityTab() {
  const [events, setEvents] = useState<TickerEvent[]>([]);

  useEffect(() => {
    const es = new EventSource("/api/events/global");
    es.onmessage = (m) => {
      try {
        const obj = JSON.parse(m.data);
        const ev: TickerEvent = {
          id: `${obj.session_id}:${obj.ts}`,
          kind: obj.kind || "system",
          text: obj.text || obj.summary || JSON.stringify(obj),
          ts: (obj.ts || Date.now()) * 1000,
        };
        setEvents((cur) => [...cur.slice(-200), ev]);
      } catch {}
    };
    return () => es.close();
  }, []);

  return (
    <div className="h-full">
      <LiveTicker events={events} maxEvents={300} />
    </div>
  );
}
```

- [ ] **Step 2: Add backend endpoint /api/events/global if missing**

Check whether `/api/events/global` SSE route exists; if not, add a simple fan-out endpoint in `api.py` that subscribes to the daemon's global event bus.

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/features/activity/ActivityTab.tsx core/claude_code_talker/api.py
git commit -m "feat(webui): ActivityTab with global SSE fan-out (Phase 27 Task 9)"
```

---

## Task 10: Wire SessionCard into SessionsPane with framer-motion AnimatePresence

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/SessionsPane.tsx` (or wherever sessions list lives)

- [ ] **Step 1: Wrap card list in AnimatePresence**

```tsx
import { AnimatePresence } from "framer-motion";
import { SessionCard } from "./SessionCard";

// inside SessionsPane:
<div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
  <AnimatePresence>
    {sessions.map((s) => <SessionCard key={s.session_id} session={s} />)}
  </AnimatePresence>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/webui/src/components/SessionsPane.tsx
git commit -m "feat(webui): AnimatePresence-wrapped session grid (Phase 27 Task 10)"
```

---

## Task 11: Resizable narration panel

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/DashboardShell.tsx` (or SessionsPane)

- [ ] **Step 1: Use react-resizable-panels for the right-rail narration**

```tsx
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

// when a session is selected, show right rail:
<PanelGroup direction="horizontal">
  <Panel defaultSize={70} minSize={40}>
    <SessionsPane />
  </Panel>
  <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-cyan-600 transition" />
  <Panel defaultSize={30} minSize={20}>
    <NarrationFeed />  {/* reuses LiveTicker */}
  </Panel>
</PanelGroup>
```

- [ ] **Step 2: Build verifies**

Run: `cd core/claude_code_talker/webui && npm run build`

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/webui/src/components/DashboardShell.tsx
git commit -m "feat(webui): resizable narration right-rail (Phase 27 Task 11)"
```

---

## Task 12: Final regression + smoke

- [ ] **Step 1: Full vitest suite passes**

Run: `cd core/claude_code_talker/webui && npx vitest run && npm run build`
Expected: all green.

- [ ] **Step 2: Backend stays green**

Run: `pytest core/tests/ -x`
Expected: all green.

- [ ] **Step 3: Manual smoke**

Open dashboard, verify:
- Top tabs render and switch
- SessionCard shows 4 zones cleanly
- Speaking dot breathes when narrator speaks
- LiveTicker filter ribbon works
- Resizable rail drags
- Preferences toggle persists across reload
- Character avatars render with persona gradients

- [ ] **Step 4: Commit any tweaks**

- [ ] **Step 5: Hand off — Phase 27 complete**

Print summary:
```
CCT v1 platform complete:
- Phase 18/19 plugin distribution  ✓
- Phase 25a Characters             ✓
- Phase 26 Markup awareness        ✓
- Phase 25c Voice cloning UX       ✓
- Phase 25b 3D mesh APIs           ✓ (with verified providers)
- Phase 27 UI/UX refinement        ✓

Open http://127.0.0.1:17832/ui-react/ to explore.
```

---

## Notes for the implementer

- Don't break existing SessionCard prop contracts — update consumers when shape shifts.
- Animations should respect `prefers-reduced-motion`. If time allows, gate `animate` props behind a `useReducedMotion()` hook.
- localStorage failures (private mode) must not crash — the hook already swallows.
- Accessibility: SpeakingDot has `aria-hidden`; SessionCard heading uses h3; LiveTicker filter buttons have role=button by default.
- Don't add a notification sound or tab title flash unless `prefs.soundEffects === true` AND the user has interacted with the page.
- DRY: every gradient/color reference goes through CSS custom props from tokens.css. Don't hardcode hex.
- YAGNI: skip a "themes/skins" feature; just sound effects + density + accent for now.
- TDD: each component task lands tests first; implementation only after they fail.
- Frequent commits: every task ends with a commit.
