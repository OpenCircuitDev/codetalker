import * as vscode from "vscode";

/**
 * Ensure Claude Code hooks for codetalker are registered.
 * Returns true if a fresh install was performed; false if already installed
 * or if the daemon couldn't be reached.
 *
 * fetchImpl is injected for testability; defaults to the global fetch.
 */
export async function ensureHooksInstalled(
  host: string,
  port: number,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const base = `http://${host}:${port}`;
  let status: { installed: boolean; settings_path: string; missing_events: string[] };
  try {
    const r = await fetchImpl(`${base}/api/hooks-status`);
    if (!r.ok) return false;
    status = (await r.json()) as { installed: boolean; settings_path: string; missing_events: string[] };
  } catch {
    return false;
  }
  if (status.installed) return false;

  try {
    const r = await fetchImpl(`${base}/api/install-hooks`, { method: "POST" });
    if (!r.ok) return false;
  } catch {
    return false;
  }

  vscode.window.showInformationMessage(
    `Codetalker installed Claude Code hooks at ${status.settings_path}. ✓`,
  );
  return true;
}
