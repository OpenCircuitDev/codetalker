import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";

export function registerChangeMode(context: vscode.ExtensionContext, client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeMode", async () => {
      const pick = await vscode.window.showQuickPick(
        [
          { label: "direct", description: "Read each turn aloud" },
          { label: "brief",  description: "LLM-translated turn summary" },
          { label: "live",   description: "Sportscaster narration as Claude works" },
        ],
        { placeHolder: "Choose Claude TTS mode" }
      );
      if (!pick) return;
      try {
        await client.callTool("tts_set_mode", { mode: pick.label });
        vscode.window.showInformationMessage(`Claude TTS mode: ${pick.label}`);
      } catch (e) {
        vscode.window.showErrorMessage(`Mode change failed: ${e}`);
      }
    })
  );
}
