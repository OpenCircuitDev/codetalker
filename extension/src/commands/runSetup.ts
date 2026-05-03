import * as vscode from "vscode";

export function registerRunSetup(ctx: vscode.ExtensionContext): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.runSetup", async () => {
      const term = vscode.window.createTerminal("Codetalker Setup");
      term.show();
      term.sendText("claude-code-talker setup", true);
    }),
  );
}
