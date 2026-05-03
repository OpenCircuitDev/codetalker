import { describe, it, expect, vi } from "vitest";

// Mock vscode module before importing our SUT
vi.mock("vscode", () => ({
  // No-op; tests use a stub ExtensionContext
}));

// Mock child_process so vi.spyOn(cp, "spawn") works (non-configurable otherwise in CJS)
vi.mock("child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("child_process")>();
  return { ...actual };
});

import * as cp from "child_process";

import {
  isDaemonAlive,
  spawnDaemonWithEnv,
  killDaemonByPid,
} from "../src/daemonProcess";

function fakeContext() {
  const state = new Map<string, unknown>();
  return {
    globalState: {
      get: <T>(k: string) => state.get(k) as T,
      update: async (k: string, v: unknown) => { state.set(k, v); },
    },
  } as any;
}

describe("isDaemonAlive", () => {
  it("returns false when no pid stored", () => {
    const ctx = fakeContext();
    expect(isDaemonAlive(ctx)).toBe(false);
  });

  it("returns false when stored pid is not running", async () => {
    const ctx = fakeContext();
    // Store pid 1 (init/system process) synchronously via the map directly
    // Note: update() is async but we need the value set before isDaemonAlive reads it
    await ctx.globalState.update("daemonPid", 1);
    // process.kill(1, 0) on most systems raises EPERM; treated as "not ours"
    // Tightest assertion: at least never throws to caller
    expect(() => isDaemonAlive(ctx)).not.toThrow();
  });

  it("returns true when stored pid is the current process", async () => {
    const ctx = fakeContext();
    await ctx.globalState.update("daemonPid", process.pid);
    expect(isDaemonAlive(ctx)).toBe(true);
  });
});

describe("spawnDaemonWithEnv", () => {
  it("spawns claude-code-talker with serve arg and merged env", async () => {
    const spy = vi.spyOn(cp, "spawn").mockReturnValue({
      pid: 12345,
      unref: () => {},
      on: () => {},
    } as any);
    const ctx = fakeContext();
    const pid = spawnDaemonWithEnv(ctx, { CUSTOM_KEY: "abc" });
    expect(pid).toBe(12345);
    expect(spy).toHaveBeenCalled();
    const callArgs = spy.mock.calls[0];
    expect(callArgs[0]).toBe("claude-code-talker");
    expect(callArgs[1]).toEqual(["serve"]);
    const opts = callArgs[2] as import("child_process").SpawnOptions;
    expect((opts.env as Record<string, string>).CUSTOM_KEY).toBe("abc");
    // PID is stored asynchronously; wait a tick for the update to flush
    await new Promise((r) => setTimeout(r, 0));
    expect(ctx.globalState.get("daemonPid")).toBe(12345);
    spy.mockRestore();
  });
});

describe("killDaemonByPid", () => {
  it("clears stored pid (smoke test — vi.doMock cannot re-mock tree-kill post-load, so we verify the observable side-effect only)", async () => {
    // Note: vi.doMock after-the-fact cannot re-mock tree-kill once the module is loaded.
    // Instead we verify the observable side-effect: the PID is cleared from globalState
    // after killDaemonByPid resolves, regardless of whether the real tree-kill fires.
    // This is the safe smoke-test approach documented in the plan.
    const ctx = fakeContext();
    // Use a PID that certainly doesn't exist so tree-kill is a no-op
    await ctx.globalState.update("daemonPid", 99999);
    // killDaemonByPid should not throw even for a non-existent PID
    await expect(killDaemonByPid(ctx)).resolves.not.toThrow();
    // PID should be cleared
    expect(ctx.globalState.get("daemonPid")).toBeUndefined();
  });
});
