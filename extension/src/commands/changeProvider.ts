import * as vscode from "vscode";
import {
  resolveActiveSessionId,
  defaultSessionFetcher,
  postSessionOverlay,
} from "../activeSession";

const PROVIDERS = ["openrouter", "gemini", "anthropic", "openai", "ollama"];

export function registerChangeProvider(
  ctx: vscode.ExtensionContext,
  host: string,
  port: number,
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeProvider", async () => {
      const sid = await resolveActiveSessionId(defaultSessionFetcher(host, port));
      if (!sid) {
        vscode.window.showWarningMessage("No active codetalker session.");
        return;
      }
      const choice = await vscode.window.showQuickPick(PROVIDERS, {
        placeHolder: "Select LLM provider for narration",
      });
      if (!choice) return;
      const ok = await postSessionOverlay(host, port, sid,
        { modes: { live: { provider: choice }, brief: { provider: choice } } });
      vscode.window.showInformationMessage(
        ok ? `Provider set to ${choice}` : `Failed to set provider`,
      );
    }),
  );
}
