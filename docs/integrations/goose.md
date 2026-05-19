# CodeTalker for Goose

Goose (Block / AAIF) is an open-source AI agent CLI with a robust extension system. It supports MCP via its extension mechanism.

## Install

### 1. Install the daemon

```bash
pip install --user claude-code-talker
```

### 2. Add codetalker as a Goose extension

Edit `~/.config/goose/config.yaml`:

```yaml
extensions:
  codetalker:
    type: stdio
    enabled: true
    cmd: codetalker-mcp
    args: []
    envs: {}
```

Alternative: use `goose configure` from the CLI — it has an interactive add-extension flow.

### 3. Verify

```bash
goose session --resume   # or start a new session
```

Inside the session, ask:

> What MCP tools do you have access to?

Goose should list the codetalker tools.

## Notes specific to Goose

- Goose's "developer mode" and "automated mode" both work with codetalker. In automated mode, codetalker's `brief` setting is recommended — Goose can run long chains, and narrating each step gets noisy.
- Goose's `multi-provider` support (OpenAI, Anthropic, Gemini, local LLMs via Ollama) is orthogonal to codetalker — narration works regardless of which LLM Goose is using.
- If you're on Goose Desktop (the GUI app), MCP servers are configured the same way; the GUI just edits the same YAML.

## What about Goose's own TTS?

Goose has a community-built voice extension. If you use both, you'll get double-narration. Pick one — codetalker has more configurability (modes, cadence, character voices) but the Goose-native extension has tighter Goose-specific event integration. Run `goose extensions list` to see what's enabled.
