import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";

export function registerChangeCadence(context: vscode.ExtensionContext, _client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeCadence", async () => {
      const pick = await vscode.window.showQuickPick(
        [
          { label: "periodic",         description: "Fire every N seconds if events present" },
          { label: "per_tool_call",    description: "Fire on every event (chattiest)" },
          { label: "per_cluster",      description: "Fire after natural idle gap" },
          { label: "significant_only", description: "Fire only on high-significance events" },
          { label: "hybrid",           description: "Significant: immediate; routine: batched" },
        ],
        { placeHolder: "Choose cadence (live mode only)" }
      );
      if (!pick) return;
      // Phase 6 V1: cadence is set in tts_workspace.yaml; this command informs the user.
      vscode.window.showInformationMessage(
        `Cadence "${pick.label}" — set in workspace config (live.cadence). Use "Edit Workspace Config" command.`
      );
    })
  );
}
