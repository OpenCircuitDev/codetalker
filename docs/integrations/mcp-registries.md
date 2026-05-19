# MCP Registry Submissions

CodeTalker is listed (or planned for listing) on the following MCP registries. This file is the **source of truth** for the listing metadata so submissions stay consistent across registries.

## Canonical metadata

```yaml
name: codetalker
display_name: CodeTalker
version: 0.2.0           # bumps with each PyPI release of claude-code-talker
description: |
  Multi-mode voice / TTS narration companion for AI coding agents. Connects to
  Claude Code, Cursor, Cline, Continue, Windsurf, Zed, Codex CLI, Goose, AWS
  Kiro, Google Antigravity, Roo Code, and Replit Agent via MCP. Free tier
  includes 4 narration modes (direct/brief/live/trigger), 5 cadence patterns
  for live mode, voice picker with Piper TTS, hook-driven narration, and a
  webui dashboard. Pro tier ($10/mo) adds character system with local voice
  cloning and animated 3D avatars.
license: MIT
homepage: https://codetalker.opencircuit.studio
repository: https://github.com/OpenCircuitDev/codetalker
maintainer: Open Circuit Studio
contact: hello@opencircuit.studio
keywords:
  - tts
  - voice
  - narration
  - ai-coding
  - accessibility
  - claude-code
  - cursor
  - cline
  - mcp
transport:
  - stdio
  - sse  # via daemon's http endpoint
install:
  pip: claude-code-talker
  entry_point: codetalker-mcp
runtime:
  language: python
  python_min: "3.11"
categories:
  - productivity
  - accessibility
  - developer-tools
```

## Per-registry submission status

| Registry | URL | Status | Notes |
|---|---|---|---|
| **registry.modelcontextprotocol.io** (official) | https://registry.modelcontextprotocol.io | TODO — submit at v1 launch | Anthropic's official registry, Sept 2025 launch. Best SEO. Submit via their GitHub PR flow against `modelcontextprotocol/registry`. |
| **PulseMCP** | https://www.pulsemcp.com | TODO — submit at v1 launch | Hand-reviewed, 14K+ servers. Form-based submission at pulsemcp.com/add. |
| **MCP.so** | https://mcp.so | TODO — submit at v1 launch | Largest catalog by volume. Self-serve listing via mcp.so/add. |
| **mcpservers.org** | https://mcpservers.org | TODO — submit at v1 launch | Curated 450+. PR to their GitHub repo. |
| **GitHub MCP Registry** | https://github.com/mcp | TODO — submit at v1 launch | GitHub's curated registry, Sept 2025. PR flow. |
| **modelcontextprotocol/servers** | https://github.com/modelcontextprotocol/servers | TODO — submit at v1 launch | Official awesome-list. PR adding codetalker to the third-party section. |
| **Anthropic Claude Marketplace** | https://claude.com/plugins | TODO — submit at v1 launch | Already have the `claude-code-plugin/` set up. Submit at v1. |
| **Continue Hub** | https://hub.continue.dev | TODO — submit at v1 launch | Continue's first-party assistant + MCP hub. Submit at hub.continue.dev/submit. |

## Submission checklist (do at v1 launch)

For each registry, file the listing with the canonical metadata above plus registry-specific niceties:

- [ ] Banner / logo PNG (1200x630 for social previews)
- [ ] Square logo PNG (256x256)
- [ ] 30-second demo GIF or MP4 showing codetalker narrating a Claude Code session
- [ ] Screenshots: webui dashboard, Pro Android session detail, character library
- [ ] Pricing page link
- [ ] GitHub issues link for support
- [ ] Discord / community link (TBD pending SP-9 launch sequence)

## Per-platform integration docs (linked from registry listings)

Each registry submission should link to the relevant per-agent integration guide so users can install codetalker with one click on their target platform. Use the live URLs at https://codetalker.opencircuit.studio/integrations/<platform> (planned in SP-6 of the launch master plan).

## When metadata changes

When bumping the version, releasing a new feature, or rebranding:
1. Update this file first.
2. Submit updates to each registry that supports it (most do via GitHub PR or admin form).
3. PulseMCP and mcpservers.org may re-review; the others auto-update from your manifest.

The weekly-landscape-scan routine (see `.claude/routines/weekly-landscape-scan.md`) watches for NEW MCP registries that emerge. If a new high-traffic registry appears, it'll generate an integration spec for adding codetalker there.
