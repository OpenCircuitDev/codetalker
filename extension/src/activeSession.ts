import * as vscode from "vscode";

export type SessionListEntry = { session_id: string; cwd: string };
export type SessionFetcher = () => Promise<SessionListEntry[]>;

/**
 * Resolve the codetalker session_id that matches the current VS Code workspace.
 * Returns null when no workspace is open or no session matches.
 *
 * The fetcher injection makes this testable without hitting the daemon.
 */
export async function resolveActiveSessionId(
  fetcher: SessionFetcher,
): Promise<string | null> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return null;
  const folderPaths = new Set(folders.map((f) => f.uri.fsPath));
  const sessions = await fetcher();
  for (const s of sessions) {
    if (folderPaths.has(s.cwd)) {
      return s.session_id;
    }
  }
  return null;
}

export function defaultSessionFetcher(host: string, port: number): SessionFetcher {
  return async () => {
    const url = `http://${host}:${port}/api/sessions`;
    const r = await fetch(url);
    if (!r.ok) return [];
    const data = (await r.json()) as { sessions?: SessionListEntry[] };
    return data.sessions ?? [];
  };
}
