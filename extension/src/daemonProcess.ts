import * as cp from "child_process";
import * as vscode from "vscode";
import treeKill from "tree-kill";

const PID_KEY = "daemonPid";

export function isDaemonAlive(ctx: vscode.ExtensionContext): boolean {
  const pid = ctx.globalState.get<number>(PID_KEY);
  if (typeof pid !== "number" || pid <= 0) return false;
  try {
    // Signal 0: existence-check on POSIX; permission-check on Windows.
    // Throws EPERM/ESRCH if not us / not running.
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function spawnDaemonWithEnv(
  ctx: vscode.ExtensionContext,
  envOverrides: Record<string, string>,
): number {
  const proc = cp.spawn("claude-code-talker", ["serve"], {
    detached: true,
    stdio: "ignore",
    shell: process.platform === "win32",
    env: { ...process.env, ...envOverrides },
  });
  proc.unref();
  const pid = proc.pid ?? 0;
  ctx.globalState.update(PID_KEY, pid);
  return pid;
}

export async function killDaemonByPid(
  ctx: vscode.ExtensionContext,
): Promise<void> {
  const pid = ctx.globalState.get<number>(PID_KEY);
  if (typeof pid !== "number" || pid <= 0) return;
  await new Promise<void>((resolve) => {
    treeKill(pid, "SIGTERM", () => resolve());
  });
  await ctx.globalState.update(PID_KEY, undefined);
}

export async function restartDaemon(
  ctx: vscode.ExtensionContext,
  envOverrides: Record<string, string>,
): Promise<number> {
  await killDaemonByPid(ctx);
  // Brief pause to let port release
  await new Promise((r) => setTimeout(r, 500));
  return spawnDaemonWithEnv(ctx, envOverrides);
}
