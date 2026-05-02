import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";

export function registerChangeRate(context: vscode.ExtensionContext, _client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeRate", async () => {
      const input = await vscode.window.showInputBox({
        prompt: "Speech rate (0.5–2.0; 1.0 = normal)",
        value: "1.05",
        validateInput: v => {
          const n = parseFloat(v);
          if (isNaN(n)) return "must be a number";
          if (n < 0.5 || n > 2.0) return "must be between 0.5 and 2.0";
          return null;
        },
      });
      if (!input) return;
      vscode.window.showInformationMessage(
        `Rate ${input} — set in workspace config (voice.rate). Use "Edit Workspace Config".`
      );
    })
  );
}
