import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";

export function registerChangeProvider(context: vscode.ExtensionContext, client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeProvider", async () => {
      try {
        const status = await client.callTool("tts_status");
        const providersMatch = status.match(/providers=\[([^\]]*)\]/);
        const providers = providersMatch
          ? providersMatch[1].split(",").map(s => s.trim().replace(/['"]/g, "")).filter(Boolean)
          : ["ollama"];
        const pick = await vscode.window.showQuickPick(providers, {
          placeHolder: "Choose LLM provider for brief/live modes",
        });
        if (!pick) return;
        vscode.window.showInformationMessage(
          `Provider "${pick}" — set in workspace config (modes.<name>.provider). Use "Edit Workspace Config".`
        );
      } catch (e) {
        vscode.window.showErrorMessage(`Provider lookup failed: ${e}`);
      }
    })
  );
}
