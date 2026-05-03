import { describe, it, expect, vi } from "vitest";

vi.mock("vscode", () => ({
  window: {
    showQuickPick: vi.fn(),
    showInformationMessage: vi.fn(),
    showWarningMessage: vi.fn(),
  },
  workspace: {
    getConfiguration: () => ({
      get: <T>(_k: string, def: T) => def,
    }),
  },
  commands: { registerCommand: vi.fn((_n: string, _h: unknown) => ({ dispose: () => {} })) },
}));

import { handleChangeMode } from "../../src/commands/changeMode";

describe("handleChangeMode", () => {
  it("aborts when no active session", async () => {
    const result = await handleChangeMode(
      "127.0.0.1", 17832,
      async () => null, // resolver returns null
      async () => true, // poster never called
    );
    expect(result).toBe("no-active-session");
  });

  it("aborts when user cancels QuickPick", async () => {
    const vscode = await import("vscode");
    (vscode.window.showQuickPick as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const result = await handleChangeMode(
      "127.0.0.1", 17832,
      async () => "sess-1",
      async () => true,
    );
    expect(result).toBe("cancelled");
  });

  it("posts the chosen mode for the active session", async () => {
    const vscode = await import("vscode");
    (vscode.window.showQuickPick as ReturnType<typeof vi.fn>).mockResolvedValueOnce("brief");
    const poster = vi.fn(async () => true);
    const result = await handleChangeMode(
      "127.0.0.1", 17832,
      async () => "sess-1",
      poster,
    );
    expect(result).toBe("ok");
    expect(poster).toHaveBeenCalledWith(
      "127.0.0.1", 17832, "sess-1", { mode: "brief" },
    );
  });
});
