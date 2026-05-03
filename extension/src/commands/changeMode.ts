import * as vscode from "vscode";
import {
  resolveActiveSessionId,
  defaultSessionFetcher,
  postSessionOverlay,
  SessionFetcher,
} from "../activeSession";

const MODES = ["live", "brief", "direct"] as const;

export type PostFn = typeof postSessionOverlay;
export type ResolverFn = (fetcher: SessionFetcher) => Promise<string | null>;

export async function handleChangeMode(
  host: string,
  port: number,
  resolver: () => Promise<string | null>,
  poster: PostFn,
): Promise<"no-active-session" | "cancelled" | "ok" | "post-failed"> {
  const sid = await resolver();
  if (!sid) {
    vscode.window.showWarningMessage(
      "No active codetalker session — open Claude Code first.",
    );
    return "no-active-session";
  }
  const choice = await vscode.window.showQuickPick([...MODES], {
    placeHolder: "Select narration mode",
  });
  if (!choice) return "cancelled";
  const ok = await poster(host, port, sid, { mode: choice });
  if (!ok) {
    vscode.window.showWarningMessage(`Failed to set mode to ${choice}`);
    return "post-failed";
  }
  vscode.window.showInformationMessage(`Mode set to ${choice}`);
  return "ok";
}

export function registerChangeMode(
  ctx: vscode.ExtensionContext,
  host: string,
  port: number,
): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("claude-tts.changeMode", async () => {
      const fetcher = defaultSessionFetcher(host, port);
      await handleChangeMode(
        host, port,
        () => resolveActiveSessionId(fetcher),
        postSessionOverlay,
      );
    }),
  );
}
