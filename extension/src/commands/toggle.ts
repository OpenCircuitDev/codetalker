import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";

export function registerToggle(context: vscode.ExtensionContext, client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.toggle", async () => {
      try {
        const status = await client.callTool("tts_status");
        const muted = status.includes("muted");
        await client.callTool(muted ? "tts_unmute" : "tts_mute");
      } catch (e) {
        vscode.window.showErrorMessage(`Claude TTS toggle failed: ${e}`);
      }
    })
  );
}
