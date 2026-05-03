import * as vscode from "vscode";
import { StatusBar } from "./statusBar";
import { isDaemonAlive, spawnDaemonWithEnv } from "./daemonProcess";
import { ensureHooksInstalled } from "./hookInstaller";
import { registerOpenWebUI } from "./commands/openWebUI";
import { registerToggle } from "./commands/toggle";

let statusBar: StatusBar | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const cfg = vscode.workspace.getConfiguration("claudeTts");
  const host = cfg.get<string>("daemonHost", "127.0.0.1");
  const port = cfg.get<number>("daemonPort", 17832);

  if (cfg.get<boolean>("autoSpawnDaemon", true)) {
    if (!isDaemonAlive(context)) {
      try {
        spawnDaemonWithEnv(context, {});
        await new Promise((r) => setTimeout(r, 1500));
      } catch {
        vscode.window.showWarningMessage("Could not auto-spawn Claude TTS daemon");
      }
    }
  }

  // Hook auto-install — silent on first activation per spec Q3 = A
  ensureHooksInstalled(host, port).catch(() => { /* best-effort */ });

  statusBar = new StatusBar();
  statusBar.start(cfg.get<number>("statusBarPollIntervalMs", 2000));
  context.subscriptions.push({ dispose: () => statusBar?.stop() });

  registerOpenWebUI(context);
  registerToggle(context, () => statusBar!.refresh());
}

export function deactivate() {
  statusBar?.stop();
}
