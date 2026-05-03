import * as vscode from "vscode";

export function registerOpenWebUI(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.openWebUI", () => {
      const cfg = vscode.workspace.getConfiguration("claudeTts");
      const host = cfg.get<string>("daemonHost", "127.0.0.1");
      const port = cfg.get<number>("daemonPort", 17832);
      const url = `http://${host}:${port}/ui/`;
      vscode.env.openExternal(vscode.Uri.parse(url));
    })
  );
}
