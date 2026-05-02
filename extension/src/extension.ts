import * as vscode from "vscode";
import { CodeTalkerClient } from "./mcpClient";
import { StatusBar } from "./statusBar";

let client: CodeTalkerClient;
let statusBar: StatusBar;

export async function activate(context: vscode.ExtensionContext) {
  client = new CodeTalkerClient();
  try {
    await client.connect();
  } catch {
    vscode.window.showWarningMessage("Claude TTS daemon not running. Start with: claude-code-talker serve");
  }

  statusBar = new StatusBar(client);
  const cfg = vscode.workspace.getConfiguration("claudeTts");
  statusBar.start(cfg.get<number>("statusBarPollIntervalMs", 2000));

  context.subscriptions.push({ dispose: () => statusBar.stop() });
}

export async function deactivate() {
  await client?.disconnect();
}
