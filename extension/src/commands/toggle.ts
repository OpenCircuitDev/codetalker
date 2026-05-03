import * as vscode from "vscode";

export function registerToggle(context: vscode.ExtensionContext, refresh: () => Promise<void>) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.toggle", async () => {
      const cfg = vscode.workspace.getConfiguration("claudeTts");
      const host = cfg.get<string>("daemonHost", "127.0.0.1");
      const port = cfg.get<number>("daemonPort", 17832);
      const baseUrl = `http://${host}:${port}`;
      try {
        const status = (await (await fetch(baseUrl + "/api/status")).json()) as { enabled: boolean };
        const next = status.enabled ? "/api/mute" : "/api/unmute";
        await fetch(baseUrl + next, { method: "POST" });
        await refresh();
      } catch (e) {
        vscode.window.showErrorMessage(`Claude TTS toggle failed: ${e}`);
      }
    })
  );
}
