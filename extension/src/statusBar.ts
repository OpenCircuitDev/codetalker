import * as vscode from "vscode";

interface StatusResponse {
  enabled: boolean;
  session_count: number;
  active_modes: Record<string, string>;
  engines: string[];
  providers: string[];
}

export class StatusBar {
  private item: vscode.StatusBarItem;
  private interval?: NodeJS.Timeout;
  private baseUrl: string;

  constructor() {
    const cfg = vscode.workspace.getConfiguration("claudeTts");
    const host = cfg.get<string>("daemonHost", "127.0.0.1");
    const port = cfg.get<number>("daemonPort", 17832);
    this.baseUrl = `http://${host}:${port}`;

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
    try {
      const res = await fetch(this.baseUrl + "/api/status");
      if (!res.ok) throw new Error(`status ${res.status}`);
      const status = (await res.json()) as StatusResponse;
      if (!status.enabled) {
        this.item.text = "$(mute) TTS off";
        this.item.tooltip = `${status.session_count} session(s); muted`;
      } else {
        const sessionCount = status.session_count;
        this.item.text = `$(unmute) TTS (${sessionCount})`;
        this.item.tooltip = `${sessionCount} active session(s); engines: ${status.engines.join(", ")}`;
      }
    } catch (e) {
      this.item.text = "$(warning) TTS offline";
      this.item.tooltip = `Daemon not reachable at ${this.baseUrl}`;
    }
  }
}
