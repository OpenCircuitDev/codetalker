import * as vscode from "vscode";
import { StatusBar } from "./statusBar";
import { isDaemonRunning, spawnDaemon } from "./daemonProcess";
import { registerOpenWebUI } from "./commands/openWebUI";
import { registerToggle } from "./commands/toggle";

let statusBar: StatusBar | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const cfg = vscode.workspace.getConfiguration("claudeTts");

  if (cfg.get<boolean>("autoSpawnDaemon", true)) {
    if (!isDaemonRunning()) {
      try {
        spawnDaemon();
        await new Promise((r) => setTimeout(r, 1500));
      } catch {
        vscode.window.showWarningMessage("Could not auto-spawn Claude TTS daemon");
      }
    }
  }

  statusBar = new StatusBar();
  statusBar.start(cfg.get<number>("statusBarPollIntervalMs", 2000));
  context.subscriptions.push({ dispose: () => statusBar?.stop() });

  registerOpenWebUI(context);
  registerToggle(context, () => statusBar!.refresh());
}

export function deactivate() {
  statusBar?.stop();
}
