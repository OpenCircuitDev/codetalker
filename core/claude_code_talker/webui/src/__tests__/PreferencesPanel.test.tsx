import { describe, expect, it, beforeEach, vi, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  describe("AR Companion pairing (CCT-31)", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("renders the pair button", () => {
      render(<PreferencesPanel />);
      expect(screen.getByRole("button", { name: /issue pairing token/i })).toBeInTheDocument();
    });

    it("issuing a token POSTs to /api/companion/pair and renders QR payload", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ token: "abc123def456ghi789jkl012mno345pqr678" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<PreferencesPanel />);
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
