import { describe, it, expect, vi } from "vitest";

vi.mock("vscode", () => ({
  window: { showInformationMessage: vi.fn() },
}));

import { ensureHooksInstalled } from "../src/hookInstaller";

describe("ensureHooksInstalled", () => {
  it("does nothing when hooks already installed", async () => {
    const fetchImpl = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => ({ installed: true, settings_path: "/x", missing_events: [] }),
    }));
    const installed = await ensureHooksInstalled("127.0.0.1", 17832, fetchImpl as any);
    expect(installed).toBe(false);
    // Should have queried status but never POSTed install
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0][0]).toContain("/api/hooks-status");
  });

  it("calls install endpoint when hooks missing", async () => {
    const calls: { url: string; method?: string }[] = [];
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
      calls.push({ url, method: init?.method });
      if (url.endsWith("/api/hooks-status")) {
        return {
          ok: true,
          json: async () => ({
            installed: false,
            settings_path: "/x/settings.json",
            missing_events: ["Stop", "Notification", "PreToolUse", "PostToolUse"],
          }),
        };
      }
      return { ok: true, json: async () => ({ installed: true, hooks_added: 4 }) };
    });
    const installed = await ensureHooksInstalled("127.0.0.1", 17832, fetchImpl as any);
    expect(installed).toBe(true);
    expect(calls.length).toBe(2);
    expect(calls[0].url).toContain("/api/hooks-status");
    expect(calls[1].url).toContain("/api/install-hooks");
    expect(calls[1].method).toBe("POST");
  });

  it("returns false on status fetch failure (non-ok response)", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    const installed = await ensureHooksInstalled("127.0.0.1", 17832, fetchImpl as any);
    expect(installed).toBe(false);
  });
});
