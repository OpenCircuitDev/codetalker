import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GlobalStatusBar } from "./components/GlobalStatusBar";
import { SessionGrid } from "./components/SessionGrid";
import { NarrationFeed } from "./components/NarrationFeed";
import { CharactersTab } from "./features/characters/CharactersTab";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 1000 } },
});

type Tab = "sessions" | "characters";

export default function App() {
  const [tab, setTab] = useState<Tab>("sessions");
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen flex flex-col">
        <GlobalStatusBar />
        <nav className="flex gap-2 px-4 py-2 border-b border-zinc-800 bg-zinc-950">
          <button
            onClick={() => setTab("sessions")}
            className={`px-3 py-1 rounded text-sm ${
              tab === "sessions" ? "bg-cyan-700 text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Sessions
          </button>
          <button
            onClick={() => setTab("characters")}
            className={`px-3 py-1 rounded text-sm ${
              tab === "characters" ? "bg-cyan-700 text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Characters
          </button>
        </nav>
        <main className="flex-1">
          {tab === "sessions" && <SessionGrid />}
          {tab === "characters" && <CharactersTab />}
        </main>
        <NarrationFeed />
      </div>
    </QueryClientProvider>
  );
}
