import * as vscode from "vscode";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";
import { storeSecret, SECRET_KEYS } from "./secretStorage";

const MIGRATION_KEY = "secretsMigrationOffered";
const SECRETS_YAML = path.join(
  os.homedir(),
  ".claude", "scripts", "codetalker", "secrets.yaml",
);

// Map secrets.yaml file_key -> env key
const FILE_TO_ENV: Record<string, string> = {
  anthropic_api_key:   "ANTHROPIC_API_KEY",
  openrouter_api_key:  "OPENROUTER_API_KEY",
  openai_api_key:      "OPENAI_API_KEY",
  elevenlabs_api_key:  "ELEVENLABS_API_KEY",
  gemini_api_key:      "GEMINI_API_KEY",
};

/**
 * If secrets.yaml exists with non-empty keys AND the user hasn't been
 * offered migration yet, prompt to move keys into the OS keychain.
 * Read-only against secrets.yaml — never modifies it.
 */
export async function maybeOfferMigration(
  ctx: vscode.ExtensionContext,
): Promise<void> {
  if (ctx.globalState.get<boolean>(MIGRATION_KEY)) return;

  let contents: string;
  try {
    contents = await fs.readFile(SECRETS_YAML, "utf-8");
  } catch {
    return; // No file, nothing to migrate
  }

  const found: Record<string, string> = {};
  for (const line of contents.split(/\r?\n/)) {
    const m = /^([a-z_]+):\s*(.+)$/.exec(line.trim());
    if (!m) continue;
    const [, fileKey, rawValue] = m;
    const value = rawValue.replace(/^["']|["']$/g, "").trim();
    const envKey = FILE_TO_ENV[fileKey];
    if (envKey && value && SECRET_KEYS.includes(envKey as any)) {
      found[envKey] = value;
    }
  }
  if (Object.keys(found).length === 0) return;

  const choice = await vscode.window.showInformationMessage(
    `Codetalker found ${Object.keys(found).length} API keys in your secrets.yaml. ` +
    `Move them to your OS keychain for safer storage?`,
    "Yes, migrate",
    "Keep both",
    "Cancel",
  );

  await ctx.globalState.update(MIGRATION_KEY, true);

  if (choice !== "Yes, migrate") return;

  let migrated = 0;
  for (const [envKey, value] of Object.entries(found)) {
    try {
      await storeSecret(ctx, envKey, value);
      migrated += 1;
    } catch {
      // Skip unknown keys silently
    }
  }
  vscode.window.showInformationMessage(
    `Codetalker migrated ${migrated} API keys to OS keychain. ` +
    `secrets.yaml is unchanged; restart the daemon to use keychain values.`,
  );
}
