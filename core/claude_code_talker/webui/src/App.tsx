// Phase 27 — top tab nav with Sessions / Characters / Markup / Activity / Preferences.
// Sessions tab shows a resizable split: session grid (left) + narration + character (right).
// v0.1.0 unification — right column is now itself a vertical split:
// LiveNarration on top, CharacterStage on bottom (the focused session's
// avatar + voice + persona). Falls back to "most recent live session"
// when no session is explicitly opened.
import React, { useEffect, useState, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useDaemonEvents } from "./hooks/useDaemonEvents";
import { GlobalStatusBar } from "./components/GlobalStatusBar";
import { SessionGrid } from "./components/SessionGrid";
import { NarrationFeed } from "./components/NarrationFeed";
import { CharacterStage } from "./components/CharacterStage";
import { PreferencesPanel } from "./components/PreferencesPanel";
import { ActivityTab } from "./features/activity/ActivityTab";
import { AnalysisTab } from "./components/AnalysisTab";
import { CTCTab } from "./components/CTCTab";
import { VoiceManager } from "./components/VoiceManager";

const CharactersTab = React.lazy(() =>
  import("./features/characters/CharactersTab").then((mod) => ({
    default: mod.CharactersTab,
  }))
);

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 1000 } },
});

type Tab = "sessions" | "ctc" | "characters" | "voices" | "activity" | "analysis" | "preferences";

const TABS: { id: Tab; label: string }[] = [
  { id: "sessions", label: "Sessions" },
  // CodeTalkerChat — Zoom-style gallery of all live sessions for quick
  // multi-session monitoring. Important precursor to the Android mode.
  // Full name in the label so users can find it without learning a TLA.
  { id: "ctc", label: "CodeTalkerChat" },
  { id: "characters", label: "Characters" },
  // Voice library promoted to its own tab so users find it without
  // hunting in Preferences.
  { id: "voices", label: "Voices" },
  { id: "activity", label: "Activity" },
  // Analysis tab — render MARKET_ANALYSIS_*.md reports for in-app glanceability.
  { id: "analysis", label: "Analysis" },
  { id: "preferences", label: "Preferences" },
];

function SessionsPane({
  openSessionId,
  setOpenSessionId,
}: {
  openSessionId: string | null;
  setOpenSessionId: (id: string | null) => void;
}) {
  // openSessionId is owned by App so it survives tab switches — clicking
  // "Manage voices →" jumps to Preferences but keeps the same session
  // expanded when the user returns. Both SessionGrid (detail panel)
  // and CharacterStage / NarrationFeed read this value.
  return (
    <PanelGroup direction="horizontal" autoSaveId="cct.sessions.split">
      <Panel defaultSize={70} minSize={40}>
        <div className="h-full overflow-auto">
          <SessionGrid
            openSessionId={openSessionId}
            onOpenSessionChange={setOpenSessionId}
          />
        </div>
      </Panel>
      <PanelResizeHandle className="w-1 bg-zinc-800 hover:bg-cyan-600 transition-colors" />
      <Panel defaultSize={30} minSize={20}>
        <PanelGroup
          direction="vertical"
          // v0.1.0 unification — v2 suffix so any stale persisted layout
          // from before the bottom-right CharacterStage was added doesn't
          // hand back a one-panel layout that puts the character pane at
          // half-screen. Bumping the key resets to the default 75/25.
          autoSaveId="cct.sessions.right.split.v2"
        >
          <Panel defaultSize={75} minSize={30}>
            <div className="h-full flex flex-col bg-[var(--color-surface-1)] border-l border-zinc-800">
              <header className="px-4 py-2 border-b border-zinc-800">
                <h2 className="text-sm font-bold text-[var(--color-text-1)]">
                  Live Narration
                  {openSessionId && (
                    <span className="ml-2 text-[10px] text-cyan-400 font-normal">
                      (filtered)
                    </span>
                  )}
                </h2>
              </header>
              <div className="flex-1 overflow-hidden">
                <NarrationFeed sessionId={openSessionId ?? undefined} />
              </div>
            </div>
          </Panel>
          <PanelResizeHandle className="h-1 bg-zinc-800 hover:bg-cyan-600 transition-colors" />
          <Panel defaultSize={25} minSize={12}>
            <div className="h-full bg-[var(--color-surface-1)] border-l border-zinc-800">
              <CharacterStage openSessionId={openSessionId} />
            </div>
          </Panel>
        </PanelGroup>
      </Panel>
    </PanelGroup>
  );
}

function DaemonEventsBridge() {
  useDaemonEvents();
  return null;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("sessions");
  // Owned at App level so it survives tab switches (B7 fix). When the
  // user opens a session row, jumps to Preferences via "Manage voices →",
  // and comes back to Sessions, the same row is still expanded.
  const [openSessionId, setOpenSessionId] = useState<string | null>(null);
  // Cross-component navigation: any component can dispatch
  //   window.dispatchEvent(new CustomEvent("cct:navigate", { detail: { tab } }))
  // to switch tabs without prop-drilling setTab through the tree. Used by
  // the "Manage voices →" link inside SessionDetailPanel.
  useEffect(() => {
    const handler = (e: Event) => {
      const target = (e as CustomEvent<{ tab?: Tab }>).detail?.tab;
      if (target && TABS.some((t) => t.id === target)) setTab(target);
    };
    window.addEventListener("cct:navigate", handler);
    return () => window.removeEventListener("cct:navigate", handler);
  }, []);
  return (
    <QueryClientProvider client={queryClient}>
      {/* v0.1.0 unification — h-screen (exactly 100vh) so the inner
          flex layout claims the full viewport height. With min-h-screen
          the container could be SHORTER than the viewport when flex
          children didn't naturally grow, leaving the bottom of the
          screen black — the "40% / half-screen" symptom. */}
      {/* Phase 4 — one SSE subscription, mounted inside the
          QueryClientProvider so the hook can invalidate the right caches.
          Replaces (via cache invalidation) the per-query 5s polling
          loops; the underlying refetchInterval timers remain as a
          safety net until Phase 6 deletes them. */}
      <DaemonEventsBridge />
      <div className="h-screen flex flex-col bg-[var(--color-surface-0)]">
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
        </nav>
        <main className="flex-1 overflow-hidden">
          {tab === "sessions" && (
            <SessionsPane
              openSessionId={openSessionId}
              setOpenSessionId={setOpenSessionId}
            />
          )}
          {tab === "ctc" && <CTCTab />}
          {tab === "characters" && (
            <Suspense fallback={<div className="text-ct-muted">Loading characters…</div>}>
              <CharactersTab />
            </Suspense>
          )}
          {tab === "voices" && (
            <div className="h-full overflow-y-auto p-6">
              <div className="max-w-5xl mx-auto">
                <header className="mb-5">
                  <h1 className="text-xl font-bold text-[var(--color-text-1)]">
                    Voice library
                  </h1>
                  <p className="text-xs text-[var(--color-text-3)] mt-1">
                    Local piper voices for narration. Install voices from the
                    curated rhasspy/piper-voices catalog, test before keeping,
                    and remove ones you don't use. Cloned voices appear here
                    after generation in the Characters tab.
                  </p>
                </header>
                <VoiceManager />
              </div>
            </div>
          )}
          {tab === "activity" && <ActivityTab />}
          {tab === "analysis" && <AnalysisTab />}
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
