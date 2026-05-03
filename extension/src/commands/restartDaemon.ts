import * as vscode from "vscode";
import { restartDaemon } from "../daemonProcess";
import { loadAllSecrets } from "../secretStorage";

export function registerRestartDaemon(ctx: vscode.ExtensionContext): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.restartDaemon", async () => {
      try {
        const env = await loadAllSecrets(ctx);
        await restartDaemon(ctx, env);
        vscode.window.showInformationMessage("Codetalker daemon restarted.");
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        vscode.window.showErrorMessage(`Restart failed: ${msg}`);
      }
    }),
  );
}
