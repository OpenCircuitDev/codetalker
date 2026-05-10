# CodeTalker for Replit Agent

Replit Agent 3 (Jan 2026) supports MCP for both custom and remote servers, with a 200-minute autonomous runtime per session.

## Important caveat: Replit is cloud-hosted

CodeTalker is **local-first** — the daemon runs on your machine and plays audio through your speakers. Replit Agent runs in Replit's cloud. So a stdio MCP connection between them isn't viable.

**Workaround:** Run the codetalker daemon locally with its HTTP+SSE endpoint exposed, then configure Replit Agent to connect to that remote MCP server.

## Install

### 1. Install the daemon locally

```bash
pip install --user claude-code-talker
```

### 2. Run the daemon with a public endpoint

Use a tunneling tool like `ngrok` to expose your local daemon's port:

```bash
claude-code-talker serve
ngrok http 17832
# note the https://abc123.ngrok.app URL ngrok prints
```

### 3. Add the remote MCP server to Replit Agent

In Replit Agent's MCP settings (Settings → MCP Connectors), add:

- **Type:** Remote (SSE)
- **URL:** `https://abc123.ngrok.app/sse`
- **Name:** `codetalker`

### 4. (Optional) Add authentication

The codetalker daemon doesn't ship with auth out of the box (it assumes local-only). For a public tunnel, you'll want either:
- A pairing token (codetalker's companion pairing system — see `docs/companion-pairing.md`)
- An ngrok password (set via `ngrok http 17832 --basic-auth user:pass`) + matching auth header in Replit's MCP config

**Security warning:** If you expose codetalker via ngrok without auth, anyone with the URL can make your machine narrate things. Treat the URL as a secret.

## Verify

In Replit Agent:

> Call codetalker's tts_status tool.

You should hear the narration locally (via your machine's speakers) and see the status text in Replit's chat.

## Notes specific to Replit

- Replit Agent's 200-minute autonomous runtime is long. codetalker's `live` mode with `cadence=per_cluster` gives you a useful narration cadence without spamming.
- Replit Agent's connectors platform (24 pre-built integrations as of 2026) is more suited to "do something in $external_service" workflows than to "narrate work locally," so codetalker is a unique fit for the auditory-feedback niche.
- If ngrok isn't an option (corporate firewall), consider running Replit's "code in browser" but executing the agent locally via codetalker's daemon + Replit's CLI export. Or wait for a future codetalker cloud edition.
