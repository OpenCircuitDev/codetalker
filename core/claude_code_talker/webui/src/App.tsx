// Phase 27 — top tab nav with Sessions / Characters / Markup / Activity / Preferences.
// Sessions tab shows a resizable split: session grid (left) + narration rail (right).
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { GlobalStatusBar } from "./components/GlobalStatusBar";
import { SessionGrid } from "./components/SessionGrid";
import { NarrationFeed } from "./components/NarrationFeed";
import { PreferencesPanel } from "./components/PreferencesPanel";
import { CharactersTab } from "./features/characters/CharactersTab";
import { ActivityTab } from "./features/activity/ActivityTab";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 1000 } },
});

type Tab = "sessions" | "characters" | "activity" | "preferences";

const TABS: { id: Tab; label: string }[] = [
  { id: "sessions", label: "Sessions" },
  { id: "characters", label: "Characters" },
  { id: "activity", label: "Activity" },
  { id: "preferences", label: "Preferences" },
];

function SessionsPane() {
  return (
    <PanelGroup direction="horizontal" autoSaveId="cct.sessions.split">
      <Panel defaultSize={70} minSize={40}>
        <div className="h-full overflow-auto">
          <SessionGrid />
        </div>
      </Panel>
      <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-cyan-600 transition-colors" />
      <Panel defaultSize={30} minSize={20}>
        <div className="h-full flex flex-col bg-[var(--color-surface-1)] border-l border-zinc-800">
          <header className="px-4 py-2 border-b border-zinc-800">
            <h2 className="text-sm font-bold text-[var(--color-text-1)]">
              Live Narration
            </h2>
          </header>
          <div className="flex-1 overflow-hidden">
            <NarrationFeed />
          </div>
        </div>
      </Panel>
    </PanelGroup>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("sessions");
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen flex flex-col bg-[var(--color-surface-0)]">
        <GlobalStatusBar />
        <nav className="flex gap-1 px-4 py-2 border-b border-zinc-800 bg-[var(--color-surface-1)]">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={
                "px-3 py-1 rounded text-sm transition-colors " +
                (tab === t.id
                  ? "bg-cyan-700 text-white"
                  : "text-[var(--color-text-2)] hover:bg-zinc-800 hover:text-[var(--color-text-1)]")
              }
            >
              {t.label}
            </button>
          ))}
          <a
            href="/ui/#markup"
            target="_blank"
            rel="noopener"
            className="px-3 py-1 rounded text-sm text-[var(--color-text-2)] hover:bg-zinc-800 hover:text-[var(--color-text-1)]"
            title="Markup settings (Phase 26)"
          >
            Markup ↗
          </a>
        </nav>
        <main className="flex-1 overflow-hidden">
          {tab === "sessions" && <SessionsPane />}
          {tab === "characters" && <CharactersTab />}
          {tab === "activity" && <ActivityTab />}
          {tab === "preferences" && (
            <div className="p-6 max-w-md">
              <PreferencesPanel />
            </div>
          )}
        </main>
      </div>
    </QueryClientProvider>
  );
}
