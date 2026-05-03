import * as vscode from "vscode";
import { SECRET_KEYS, storeSecret, loadAllSecrets } from "../secretStorage";
import { restartDaemon } from "../daemonProcess";

export function registerSetSecret(ctx: vscode.ExtensionContext): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.setSecret", async () => {
      const key = await vscode.window.showQuickPick([...SECRET_KEYS], {
        placeHolder: "Select the API key to set",
      });
      if (!key) return;
      const value = await vscode.window.showInputBox({
        prompt: `Value for ${key}`,
        password: true,
        ignoreFocusOut: true,
      });
      if (!value) return;
      await storeSecret(ctx, key, value);
      const env = await loadAllSecrets(ctx);
      await restartDaemon(ctx, env);
      vscode.window.showInformationMessage(
        `Stored ${key} in OS keychain and restarted daemon.`,
      );
    }),
  );
}
