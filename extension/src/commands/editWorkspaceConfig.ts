import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";
import { readWorkspaceConfig, writeWorkspaceConfig } from "../workspaceConfig";

export function registerEditWorkspaceConfig(context: vscode.ExtensionContext, client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.editWorkspaceConfig", async () => {
      const cfg = readWorkspaceConfig();

      const mode = await vscode.window.showQuickPick(["direct", "brief", "live"],
        { placeHolder: `Mode (current: ${cfg.mode || "direct"})` });
      if (!mode) return;
      cfg.mode = mode;

      // Voice
      const voicesRaw = await client.callTool("tts_list_voices").catch(() => "");
      const voices = voicesRaw.split(",").map((v: string) => v.trim()).filter(Boolean);
      if (voices.length > 0) {
        const voice = await vscode.window.showQuickPick(voices,
          { placeHolder: `Voice (current: ${cfg.voice || voices[0]})` });
        if (voice) cfg.voice = voice;
      }

      // Rate
      const rateStr = await vscode.window.showInputBox({
        prompt: `Rate (0.5–2.0; current: ${cfg.rate ?? 1.05})`,
        value: String(cfg.rate ?? 1.05),
      });
      if (rateStr) {
        const rate = parseFloat(rateStr);
        if (!isNaN(rate) && rate >= 0.5 && rate <= 2.0) {
          cfg.rate = rate;
        }
      }

      // Prose level (only for direct/brief)
      if (mode === "direct" || mode === "brief") {
        const prose = await vscode.window.showQuickPick(["full", "conclusions", "none"],
          { placeHolder: "Prose level" });
        if (prose) cfg.prose = prose;
      }

      // Synopsis
      const synopsis = await vscode.window.showQuickPick(["full", "brief", "none"],
        { placeHolder: "Synopsis" });
      if (synopsis) cfg.synopsis = synopsis;

      // Cadence (live only)
      if (mode === "live") {
        const cadence = await vscode.window.showQuickPick(
          ["periodic", "per_tool_call", "per_cluster", "significant_only", "hybrid"],
          { placeHolder: "Cadence strategy" });
        if (cadence) cfg.live_cadence = cadence;
      }

      // Element switches
      const codeBlocks = await vscode.window.showQuickPick(["stub", "speak"],
        { placeHolder: "Code blocks" });
      if (codeBlocks) cfg.code_blocks = codeBlocks;

      const filePaths = await vscode.window.showQuickPick(["filename", "omit"],
        { placeHolder: "File paths in prose" });
      if (filePaths) cfg.file_paths = filePaths;

      // Save
      const save = await vscode.window.showQuickPick(["yes (write tts_workspace.yaml)", "cancel"],
        { placeHolder: "Save?" });
      if (save && save.startsWith("yes")) {
        writeWorkspaceConfig(cfg);
        vscode.window.showInformationMessage("Workspace config saved. Restart daemon for changes to take effect.");
      }
    })
  );
}
