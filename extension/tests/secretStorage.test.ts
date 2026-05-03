import { describe, it, expect, vi } from "vitest";

vi.mock("vscode", () => ({}));

import {
  SECRET_KEYS,
  loadAllSecrets,
  storeSecret,
} from "../src/secretStorage";

function fakeContext() {
  const store = new Map<string, string>();
  return {
    secrets: {
      get: async (k: string) => store.get(k),
      store: async (k: string, v: string) => { store.set(k, v); },
      delete: async (k: string) => { store.delete(k); },
    },
  } as any;
}

describe("SECRET_KEYS", () => {
  it("includes the five known provider keys", () => {
    expect(SECRET_KEYS).toContain("ANTHROPIC_API_KEY");
    expect(SECRET_KEYS).toContain("OPENROUTER_API_KEY");
    expect(SECRET_KEYS).toContain("OPENAI_API_KEY");
    expect(SECRET_KEYS).toContain("ELEVENLABS_API_KEY");
    expect(SECRET_KEYS).toContain("GEMINI_API_KEY");
    expect(SECRET_KEYS.length).toBe(5);
  });
});

describe("loadAllSecrets", () => {
  it("returns empty record when nothing stored", async () => {
    const ctx = fakeContext();
    const env = await loadAllSecrets(ctx);
    expect(env).toEqual({});
  });

  it("returns only keys that have been stored", async () => {
    const ctx = fakeContext();
    await ctx.secrets.store("ANTHROPIC_API_KEY", "sk-ant-foo");
    await ctx.secrets.store("OPENAI_API_KEY", "sk-oai-bar");
    const env = await loadAllSecrets(ctx);
    expect(env.ANTHROPIC_API_KEY).toBe("sk-ant-foo");
    expect(env.OPENAI_API_KEY).toBe("sk-oai-bar");
    expect(env.GEMINI_API_KEY).toBeUndefined();
  });
});

describe("storeSecret", () => {
  it("rejects unknown keys", async () => {
    const ctx = fakeContext();
    await expect(storeSecret(ctx, "BOGUS_KEY", "x")).rejects.toThrow();
  });

  it("stores known keys", async () => {
    const ctx = fakeContext();
    await storeSecret(ctx, "ELEVENLABS_API_KEY", "el-xxx");
    expect(await ctx.secrets.get("ELEVENLABS_API_KEY")).toBe("el-xxx");
  });
});
