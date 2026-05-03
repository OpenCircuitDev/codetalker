import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";

export function registerViewLog(ctx: vscode.ExtensionContext): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.viewLog", async () => {
      const logPath = path.join(
        os.homedir(),
        ".claude", "scripts", "codetalker", "daemon.log",
      );
      try {
        const doc = await vscode.workspace.openTextDocument(logPath);
        await vscode.window.showTextDocument(doc, { preview: false });
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        vscode.window.showWarningMessage(
          `Cannot open daemon log at ${logPath}: ${msg}`,
        );
      }
    }),
  );
}
