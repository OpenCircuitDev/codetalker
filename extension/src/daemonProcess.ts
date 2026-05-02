import * as cp from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

const PIDFILE = path.join(os.homedir(), ".claude", "scripts", "codetalker.pid");

export function isDaemonRunning(): boolean {
  if (!fs.existsSync(PIDFILE)) return false;
  try {
    const pid = parseInt(fs.readFileSync(PIDFILE, "utf-8").trim(), 10);
    if (isNaN(pid)) return false;
    process.kill(pid, 0);  // throws if not alive
    return true;
  } catch {
    return false;
  }
}

export function spawnDaemon(): void {
  const proc = cp.spawn("claude-code-talker", ["serve"], {
    detached: true,
    stdio: "ignore",
    shell: process.platform === "win32",
  });
  proc.unref();
}
