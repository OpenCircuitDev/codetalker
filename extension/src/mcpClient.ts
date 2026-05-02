import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import * as vscode from "vscode";

export class CodeTalkerClient {
  private client: Client | null = null;

  async connect(): Promise<void> {
    const cfg = vscode.workspace.getConfiguration("claudeTts");
    const host = cfg.get<string>("daemonHost", "127.0.0.1");
    const port = cfg.get<number>("daemonPort", 17832);
    const url = new URL(`http://${host}:${port}/sse`);
    const transport = new SSEClientTransport(url);
    this.client = new Client({ name: "claude-tts-vscode", version: "0.1.0" });
    await this.client.connect(transport);
  }

  isConnected(): boolean {
    return this.client !== null;
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<string> {
    if (!this.client) throw new Error("not connected");
    const result = await this.client.callTool({ name, arguments: args });
    const content = result.content as any[];
    for (const c of content) {
      if (c.type === "text") return c.text;
    }
    return "";
  }

  async disconnect(): Promise<void> {
    await this.client?.close();
    this.client = null;
  }
}
