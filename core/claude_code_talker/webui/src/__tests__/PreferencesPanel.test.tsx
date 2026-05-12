import { describe, expect, it, beforeEach, vi, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PreferencesPanel } from "../components/PreferencesPanel";

// v0.1.0 unification: PreferencesPanel now uses react-query for the
// fleet audio-defaults toggle, so every render needs a QueryClient
// in context. Use a fresh client per test so cached data doesn't leak.
function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PreferencesPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    // Stub fetch so the audio-defaults useQuery doesn't hit real network
    // and so the AR pairing tests can override per-call as needed.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          companion_suppress_desktop: false,
          default_outputs: ["desktop", "phone", "glasses"],
        }),
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders sound effects toggle off by default", () => {
    renderWithQuery(<PreferencesPanel />);
    const toggle = screen.getByLabelText(/sound effects/i) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
  });

  it("toggling sound effects persists", () => {
    renderWithQuery(<PreferencesPanel />);
    const toggle = screen.getByLabelText(/sound effects/i);
    fireEvent.click(toggle);
    expect(localStorage.getItem("cct.prefs")).toContain("\"soundEffects\":true");
  });

  it("density radio updates pref", () => {
    renderWithQuery(<PreferencesPanel />);
    fireEvent.click(screen.getByLabelText(/compact/i));
    expect(localStorage.getItem("cct.prefs")).toContain("\"density\":\"compact\"");
  });

  describe("AR Companion pairing (CCT-31)", () => {
    it("renders the pair button", () => {
      renderWithQuery(<PreferencesPanel />);
      expect(screen.getByRole("button", { name: /issue pairing token/i })).toBeInTheDocument();
    });

    it("issuing a token POSTs to /api/companion/pair and renders QR payload", async () => {
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (typeof url === "string" && url.startsWith("/api/cfg/audio-defaults")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              companion_suppress_desktop: false,
              default_outputs: ["desktop", "phone", "glasses"],
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ token: "abc123def456ghi789jkl012mno345pqr678" }),
        });
      });
      vi.stubGlobal("fetch", fetchMock);

      renderWithQuery(<PreferencesPanel />);
      const btn = screen.getByRole("button", { name: /issue pairing token/i });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/companion/pair",
          expect.objectContaining({ method: "POST" })
        );
      });
      // QR section appears after the token resolves.
      await waitFor(() => {
        expect(screen.getByText(/scan with the codetalker android app/i)).toBeInTheDocument();
      });
    });
  });
});
