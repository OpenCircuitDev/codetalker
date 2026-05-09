// Phase 27 — top tab nav with Sessions / Characters / Markup / Activity / Preferences.
// Markup is an external link to the legacy /ui/#markup pane (Phase 26).
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
        <main className="flex-1 overflow-auto">
          {tab === "sessions" && <SessionGrid />}
          {tab === "characters" && <CharactersTab />}
          {tab === "activity" && <ActivityTab />}
          {tab === "preferences" && (
            <div className="p-6 max-w-md">
              <PreferencesPanel />
            </div>
          )}
        </main>
        {tab === "sessions" && <NarrationFeed />}
      </div>
    </QueryClientProvider>
  );
}
