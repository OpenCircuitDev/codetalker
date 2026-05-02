import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  vscode.window.showInformationMessage("Claude Code Talker extension activated");
}

export function deactivate() {}
