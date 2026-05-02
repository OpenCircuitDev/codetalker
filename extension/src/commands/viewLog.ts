import * as vscode from "vscode";
import * as os from "os";
import * as path from "path";

const LOG_PATH = path.join(os.homedir(), ".claude", "scripts", "codetalker.log");

export function registerViewLog(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.viewLog", async () => {
      try {
        const doc = await vscode.workspace.openTextDocument(LOG_PATH);
        await vscode.window.showTextDocument(doc);
      } catch (e) {
        vscode.window.showErrorMessage(`Could not open log at ${LOG_PATH}: ${e}`);
      }
    })
  );
}
