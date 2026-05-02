import * as vscode from "vscode";
import { CodeTalkerClient } from "./mcpClient";
import { StatusBar } from "./statusBar";
import { isDaemonRunning, spawnDaemon } from "./daemonProcess";

let client: CodeTalkerClient;
let statusBar: StatusBar;

export async function activate(context: vscode.ExtensionContext) {
  const cfg = vscode.workspace.getConfiguration("claudeTts");

  if (cfg.get<boolean>("autoSpawnDaemon", true)) {
    if (!isDaemonRunning()) {
      try {
        spawnDaemon();
        await new Promise(r => setTimeout(r, 1500));
      } catch {
        vscode.window.showWarningMessage("Could not auto-spawn Claude TTS daemon");
      }
    }
  }

  client = new CodeTalkerClient();
  try {
    await client.connect();
  } catch {
    vscode.window.showWarningMessage("Claude TTS daemon not running. Start with: claude-code-talker serve");
  }

  statusBar = new StatusBar(client);
  statusBar.start(cfg.get<number>("statusBarPollIntervalMs", 2000));

  context.subscriptions.push({ dispose: () => statusBar.stop() });
}

export async function deactivate() {
  await client?.disconnect();
}
