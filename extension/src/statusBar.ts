import * as vscode from "vscode";
import { CodeTalkerClient } from "./mcpClient";

export class StatusBar {
  private item: vscode.StatusBarItem;
  private interval?: NodeJS.Timeout;

  constructor(private client: CodeTalkerClient) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.command = "claude-tts.toggle";
    this.item.show();
    this.refresh();
  }

  start(intervalMs: number) {
    this.interval = setInterval(() => this.refresh(), intervalMs);
  }

  stop() {
    if (this.interval) clearInterval(this.interval);
    this.item.dispose();
  }

  async refresh() {
    if (!this.client.isConnected()) {
      this.item.text = "$(warning) TTS offline";
      this.item.tooltip = "Daemon not reachable. Click to attempt connection.";
      return;
    }
    try {
      const status = await this.client.callTool("tts_status");
      // Parse: "mode=monitor, enabled, engines=[...], providers=[...]"
      const isMuted = status.includes("muted");
      const modeMatch = status.match(/mode=(\w+)/);
      const mode = modeMatch ? modeMatch[1] : "?";
      if (isMuted) {
        this.item.text = "$(mute) TTS off";
      } else {
        this.item.text = `$(unmute) TTS ${mode}`;
      }
      this.item.tooltip = status;
    } catch (e) {
      this.item.text = "$(warning) TTS error";
      this.item.tooltip = `Error: ${e}`;
    }
  }
}
