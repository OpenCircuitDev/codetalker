import * as vscode from "vscode";
import { CodeTalkerClient } from "../mcpClient";
import { isDaemonRunning, spawnDaemon } from "../daemonProcess";

export function registerRestartDaemon(context: vscode.ExtensionContext, client: CodeTalkerClient) {
  context.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.restartDaemon", async () => {
      try {
        await client.callTool("tts_shutdown");
      } catch {
        // Daemon may have already exited; that's OK
      }
      await client.disconnect();
      // Wait for daemon to stop
      for (let i = 0; i < 20; i++) {
        if (!isDaemonRunning()) break;
        await new Promise(r => setTimeout(r, 200));
      }
      try {
        spawnDaemon();
        await new Promise(r => setTimeout(r, 1500));
        await client.connect();
        vscode.window.showInformationMessage("Claude TTS daemon restarted");
      } catch (e) {
        vscode.window.showErrorMessage(`Restart failed: ${e}`);
      }
    })
  );
}
