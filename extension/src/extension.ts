import * as vscode from "vscode";
import { CodeTalkerClient } from "./mcpClient";
import { StatusBar } from "./statusBar";
import { isDaemonRunning, spawnDaemon } from "./daemonProcess";
import { registerToggle } from "./commands/toggle";
import { registerChangeMode } from "./commands/changeMode";
import { registerChangeVoice } from "./commands/changeVoice";
import { registerChangeCadence } from "./commands/changeCadence";
import { registerChangeProvider } from "./commands/changeProvider";
import { registerChangeRate } from "./commands/changeRate";
import { registerRestartDaemon } from "./commands/restartDaemon";
import { registerViewLog } from "./commands/viewLog";
import { registerRunSetup } from "./commands/runSetup";
import { registerEditWorkspaceConfig } from "./commands/editWorkspaceConfig";

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

  // Command Palette commands
  registerToggle(context, client);
  registerChangeMode(context, client);
  registerChangeVoice(context, client);
  registerChangeCadence(context, client);
  registerChangeProvider(context, client);
  registerChangeRate(context, client);
  registerEditWorkspaceConfig(context, client);
  registerRestartDaemon(context, client);
  registerViewLog(context);
  registerRunSetup(context);
}

export async function deactivate() {
  await client?.disconnect();
}
