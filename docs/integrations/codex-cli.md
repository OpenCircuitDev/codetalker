# CodeTalker for Codex CLI

OpenAI Codex CLI (`@openai/codex`) added MCP support in late 2025. CodeTalker hooks in as an MCP server.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add to Codex's config

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.codetalker]
command = "codetalker-mcp"
args = []
```

If `codetalker-mcp` isn't on Codex's PATH (Codex CLI sometimes sandboxes its env), use absolute:

```toml
[mcp_servers.codetalker]
command = "/Users/you/.local/bin/codetalker-mcp"
args = []
```

### 3. Restart Codex

```bash
codex --version    # verify Codex picks up the new MCP server
```

In an interactive session, run `/mcp list` (if Codex's CLI supports it) to confirm codetalker is loaded.

## Verify

In a Codex CLI session:

> Call codetalker tts_status.

Codex should invoke the MCP tool and return its output.

## Notes specific to Codex CLI

- Codex CLI ships with Windows PowerShell + WSL2 sandbox support as of Q1 2026 — codetalker's daemon runs on the host, so the MCP shim crosses the sandbox boundary via stdio. This works in WSL2 if Python is installed on the WSL side.
- Codex CLI's container-caching speedup (90% faster cold-starts as of 2026) doesn't affect codetalker — the shim is fast either way; the daemon is a long-running singleton.
- If you primarily use Codex Cloud (the cloud-hosted variant), codetalker won't work there — codetalker is local-first by design (audio plays on your machine). Run Codex locally or via Codex CLI for codetalker integration.
