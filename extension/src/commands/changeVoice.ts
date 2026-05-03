import * as vscode from "vscode";
import {
  resolveActiveSessionId,
  defaultSessionFetcher,
  postSessionOverlay,
} from "../activeSession";

export function registerChangeVoice(
  ctx: vscode.ExtensionContext,
  host: string,
  port: number,
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeVoice", async () => {
      const fetcher = defaultSessionFetcher(host, port);
      const sid = await resolveActiveSessionId(fetcher);
      if (!sid) {
        vscode.window.showWarningMessage("No active codetalker session.");
        return;
      }
      const r = await fetch(`http://${host}:${port}/api/catalog`);
      const catalog = r.ok ? (await r.json()) as { voices?: { id?: string; name?: string }[] } : { voices: [] };
      const voiceList: string[] = (catalog.voices ?? []).map((v) => v.id ?? v.name ?? "");
      if (voiceList.length === 0) {
        vscode.window.showWarningMessage("No voices available from daemon.");
        return;
      }
      const choice = await vscode.window.showQuickPick(voiceList, {
        placeHolder: "Select voice",
      });
      if (!choice) return;
      const ok = await postSessionOverlay(host, port, sid, { voice: { model: choice } });
      vscode.window.showInformationMessage(
        ok ? `Voice set to ${choice}` : `Failed to set voice`,
      );
    }),
  );
}
