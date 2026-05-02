import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import * as yaml from "js-yaml";

export function getWorkspaceConfigPath(): string | null {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return null;
  return path.join(folders[0].uri.fsPath, ".claude", "tts_workspace.yaml");
}

export function readWorkspaceConfig(): Record<string, any> {
  const p = getWorkspaceConfigPath();
  if (!p || !fs.existsSync(p)) return {};
  try {
    return (yaml.load(fs.readFileSync(p, "utf-8")) as Record<string, any>) || {};
  } catch {
    return {};
  }
}

export function writeWorkspaceConfig(cfg: Record<string, any>): void {
  const p = getWorkspaceConfigPath();
  if (!p) {
    vscode.window.showErrorMessage("No workspace folder open; cannot save config");
    return;
  }
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, yaml.dump(cfg, { lineWidth: 100 }), "utf-8");
}
