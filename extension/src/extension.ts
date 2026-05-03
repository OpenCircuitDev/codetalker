import * as vscode from "vscode";
import { StatusBar } from "./statusBar";
import { isDaemonAlive, spawnDaemonWithEnv } from "./daemonProcess";
import { ensureHooksInstalled } from "./hookInstaller";
import { loadAllSecrets } from "./secretStorage";
import { maybeOfferMigration } from "./migrationPrompt";
import { registerOpenWebUI } from "./commands/openWebUI";
import { registerToggle } from "./commands/toggle";
import { registerSetSecret } from "./commands/setSecret";
import { registerChangeMode } from "./commands/changeMode";
import { registerChangeVoice } from "./commands/changeVoice";
import { registerChangeCadence } from "./commands/changeCadence";
import { registerChangeProvider } from "./commands/changeProvider";
import { registerChangeRate } from "./commands/changeRate";
import { registerEditWorkspaceConfig } from "./commands/editWorkspaceConfig";
import { registerRestartDaemon } from "./commands/restartDaemon";
import { registerViewLog } from "./commands/viewLog";
import { registerRunSetup } from "./commands/runSetup";

let statusBar: StatusBar | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const cfg = vscode.workspace.getConfiguration("claudeTts");
  const host = cfg.get<string>("daemonHost", "127.0.0.1");
  const port = cfg.get<number>("daemonPort", 17832);

  if (cfg.get<boolean>("autoSpawnDaemon", true)) {
    if (!isDaemonAlive(context)) {
      try {
        const env = await loadAllSecrets(context);
        spawnDaemonWithEnv(context, env);
        await new Promise((r) => setTimeout(r, 1500));
      } catch {
        vscode.window.showWarningMessage("Could not auto-spawn Claude TTS daemon");
      }
    }
  }

  ensureHooksInstalled(host, port).catch(() => {});
  maybeOfferMigration(context).catch(() => {});

  statusBar = new StatusBar();
  statusBar.start(cfg.get<number>("statusBarPollIntervalMs", 2000));
  context.subscriptions.push({ dispose: () => statusBar?.stop() });

  registerOpenWebUI(context);
  registerToggle(context, () => statusBar!.refresh());
  registerSetSecret(context);
  registerChangeMode(context, host, port);
  registerChangeVoice(context, host, port);
  registerChangeCadence(context, host, port);
  registerChangeProvider(context, host, port);
  registerChangeRate(context, host, port);
  registerEditWorkspaceConfig(context);
  registerRestartDaemon(context);
  registerViewLog(context);
  registerRunSetup(context);
}

export function deactivate() {
  statusBar?.stop();
}
