import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GlobalStatusBar } from "./components/GlobalStatusBar";
import { SessionGrid } from "./components/SessionGrid";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 1000 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen flex flex-col">
        <GlobalStatusBar />
        <main className="flex-1">
          <SessionGrid />
        </main>
      </div>
    </QueryClientProvider>
  );
}
