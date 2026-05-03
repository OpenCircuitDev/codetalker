import * as vscode from "vscode";
import {
  resolveActiveSessionId,
  defaultSessionFetcher,
  postSessionOverlay,
} from "../activeSession";

const CADENCES = [
  "periodic", "per_tool_call", "per_cluster", "significant_only", "hybrid",
];

export function registerChangeCadence(
  ctx: vscode.ExtensionContext,
  host: string,
  port: number,
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeCadence", async () => {
      const sid = await resolveActiveSessionId(defaultSessionFetcher(host, port));
      if (!sid) {
        vscode.window.showWarningMessage("No active codetalker session.");
        return;
      }
      const choice = await vscode.window.showQuickPick(CADENCES, {
        placeHolder: "Select cadence strategy",
      });
      if (!choice) return;
      const ok = await postSessionOverlay(host, port, sid,
        { live: { cadence_strategy: choice } });
      vscode.window.showInformationMessage(
        ok ? `Cadence set to ${choice}` : `Failed to set cadence`,
      );
    }),
  );
}
