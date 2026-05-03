import * as vscode from "vscode";
import {
  resolveActiveSessionId,
  defaultSessionFetcher,
  postSessionOverlay,
} from "../activeSession";

export function registerChangeRate(
  ctx: vscode.ExtensionContext,
  host: string,
  port: number,
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeRate", async () => {
      const sid = await resolveActiveSessionId(defaultSessionFetcher(host, port));
      if (!sid) {
        vscode.window.showWarningMessage("No active codetalker session.");
        return;
      }
      const input = await vscode.window.showInputBox({
        prompt: "Speech rate (0.5–2.0, default 1.0)",
        value: "1.0",
        validateInput: (v) => {
          const n = Number(v);
          if (Number.isNaN(n) || n < 0.5 || n > 2.0) {
            return "Must be a number between 0.5 and 2.0";
          }
          return null;
        },
      });
      if (!input) return;
      const rate = Number(input);
      const ok = await postSessionOverlay(host, port, sid, { voice: { rate } });
      vscode.window.showInformationMessage(
        ok ? `Rate set to ${rate}x` : `Failed to set rate`,
      );
    }),
  );
}
