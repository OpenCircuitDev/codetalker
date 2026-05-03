import * as vscode from "vscode";

export const SECRET_KEYS = [
  "ANTHROPIC_API_KEY",
  "OPENROUTER_API_KEY",
  "OPENAI_API_KEY",
  "ELEVENLABS_API_KEY",
  "GEMINI_API_KEY",
] as const;

export type SecretKey = (typeof SECRET_KEYS)[number];

/**
 * Read every codetalker-known API key from the host OS keychain via
 * vscode.SecretStorage. Returns a record suitable for env injection
 * when spawning the daemon process.
 */
export async function loadAllSecrets(
  ctx: vscode.ExtensionContext,
): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  for (const k of SECRET_KEYS) {
    const v = await ctx.secrets.get(k);
    if (v) out[k] = v;
  }
  return out;
}

export async function storeSecret(
  ctx: vscode.ExtensionContext,
  key: string,
  value: string,
): Promise<void> {
  if (!SECRET_KEYS.includes(key as SecretKey)) {
    throw new Error(`unknown secret key: ${key}`);
  }
  await ctx.secrets.store(key, value);
}

export async function deleteSecret(
  ctx: vscode.ExtensionContext,
  key: string,
): Promise<void> {
  if (!SECRET_KEYS.includes(key as SecretKey)) {
    throw new Error(`unknown secret key: ${key}`);
  }
  await ctx.secrets.delete(key);
}
