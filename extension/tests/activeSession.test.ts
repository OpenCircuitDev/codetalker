import { describe, it, expect, vi } from "vitest";

vi.mock("vscode", () => ({
  workspace: {
    workspaceFolders: undefined as { uri: { fsPath: string } }[] | undefined,
  },
}));

import { resolveActiveSessionId } from "../src/activeSession";

describe("resolveActiveSessionId", () => {
  it("returns null when no workspace folder is open", async () => {
    const id = await resolveActiveSessionId(async () => []);
    expect(id).toBeNull();
  });

  it("returns the session id whose cwd matches a workspace folder", async () => {
    const vscode = await import("vscode");
    (vscode.workspace as any).workspaceFolders = [
      { uri: { fsPath: "C:/Users/brand/myproject" } },
    ];
    const id = await resolveActiveSessionId(async () => [
      { session_id: "abc-123", cwd: "C:/Users/brand/myproject" },
      { session_id: "def-456", cwd: "C:/Users/brand/other" },
    ]);
    expect(id).toBe("abc-123");
  });

  it("returns null when no session matches any workspace folder", async () => {
    const vscode = await import("vscode");
    (vscode.workspace as any).workspaceFolders = [
      { uri: { fsPath: "C:/Users/brand/orphan" } },
    ];
    const id = await resolveActiveSessionId(async () => [
      { session_id: "abc-123", cwd: "C:/Users/brand/myproject" },
    ]);
    expect(id).toBeNull();
  });
});
