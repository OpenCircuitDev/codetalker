import * as vscode from "vscode";
import * as fs from "fs/promises";
import * as path from "path";

export function registerEditWorkspaceConfig(
  ctx: vscode.ExtensionContext,
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.editWorkspaceConfig", async () => {
      const folder = vscode.workspace.workspaceFolders?.[0];
      if (!folder) {
        vscode.window.showWarningMessage("Open a workspace folder first.");
        return;
      }
      const target = path.join(folder.uri.fsPath, ".claude", "tts_workspace.yaml");

      const mode = await vscode.window.showQuickPick(
        ["live", "brief", "direct"],
        { placeHolder: "1/4: Mode" },
      );
      if (!mode) return;

      const verbosity = await vscode.window.showQuickPick(
        ["concise", "standard", "expanded"],
        { placeHolder: "2/4: Verbosity" },
      );
      if (!verbosity) return;

      const teacherEnabled = await vscode.window.showQuickPick(
        ["on", "off"],
        { placeHolder: "3/4: Teacher mode" },
      );
      if (!teacherEnabled) return;

      const provider = await vscode.window.showQuickPick(
        ["openrouter", "gemini", "anthropic", "openai", "ollama"],
        { placeHolder: "4/4: LLM provider" },
      );
      if (!provider) return;

      const yaml =
`# .claude/tts_workspace.yaml — codetalker per-workspace overrides
mode: ${mode}
teacher_mode:
  enabled: ${teacherEnabled === "on"}
  verbosity: ${verbosity}
modes:
  live:
    provider: ${provider}
  brief:
    provider: ${provider}
`;
      await fs.mkdir(path.dirname(target), { recursive: true });
      await fs.writeFile(target, yaml, "utf-8");
      const doc = await vscode.workspace.openTextDocument(target);
      await vscode.window.showTextDocument(doc);
      vscode.window.showInformationMessage(`Wrote ${target}`);
    }),
  );
}
