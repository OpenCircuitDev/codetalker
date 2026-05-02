import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";

export function registerChangeVoice(context: vscode.ExtensionContext, client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeVoice", async () => {
      try {
        const voicesRaw = await client.callTool("tts_list_voices");
        const voices = voicesRaw.split(",").map(v => v.trim()).filter(Boolean);
        if (voices.length === 0) {
          vscode.window.showWarningMessage("No voices installed");
          return;
        }
        const pick = await vscode.window.showQuickPick(voices, {
          placeHolder: "Choose voice",
        });
        if (!pick) return;
        // Phase 6 V1: speak a sample with the chosen voice (workspace-write lands in Task 13)
        await client.callTool("tts_speak", {
          text: `This is the ${pick} voice.`,
        });
      } catch (e) {
        vscode.window.showErrorMessage(`Voice change failed: ${e}`);
      }
    })
  );
}
