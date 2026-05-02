import * as vscode from "vscode";

export function registerRunSetup(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.runSetup", () => {
      const term = vscode.window.createTerminal("Claude TTS Setup");
      term.show();
      term.sendText("claude-code-talker-setup");
    })
  );
}
