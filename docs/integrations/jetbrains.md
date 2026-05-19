# CodeTalker for JetBrains AI Assistant

**Status:** Coming in v1.x (SP-10 of the launch master plan).

JetBrains AI Assistant ships with the JetBrains IDE family (IntelliJ IDEA, PyCharm, WebStorm, GoLand, Rider, etc.). It is not MCP-native as of mid-2026, so codetalker-for-JetBrains requires a bespoke plugin.

## Planned mechanism

A JetBrains IDE plugin (Kotlin, built against the IntelliJ Platform SDK) that:

1. Listens for JetBrains AI Assistant events (chat message, code action invoked, agent step completed)
2. Invokes the local codetalker daemon's HTTP narration endpoint
3. Lives in plugins.jetbrains.com under the OpenCircuit publisher

Distribution will be via the JetBrains Plugin Marketplace — search "CodeTalker" inside any JetBrains IDE's Settings → Plugins → Marketplace.

## Why this approach

JetBrains AI Assistant uses the JetBrains plugin extension points, not an open protocol. To integrate, codetalker needs to be a JetBrains plugin. The plugin will be thin — most logic lives in the codetalker daemon; the plugin is just an event listener + REST caller.

## Timeline

The JetBrains plugin is part of SP-10 in the launch master plan, scheduled after v1 launch. It's one of the two **Pro Plus** ($3/mo addon) platform integrations along with Aider.

## What about Junie?

JetBrains shipped **Junie** (April 2025) — an autonomous coding agent that runs longer-form tasks. Junie uses the same plugin extension points as JetBrains AI Assistant, so the codetalker plugin will support both.

Junie's autonomous-mode narration is a perfect fit for codetalker's `live` mode + `cadence=significant_only` — let Junie run for an hour and only hear about the milestones.

## Notes for the JetBrains AI Assistant free tier

JetBrains AI Assistant moved to a free tier in 2025.1+ (with limited cloud quota). codetalker has no quota interaction — narration is local and unmetered. The Pro Plus subscription needed to unlock the JetBrains adapter is separate from any JetBrains AI subscription.

## What about other JetBrains AI products?

- **JetBrains Junie** — same plugin (see above)
- **Sourcegraph Cody** for JetBrains — separate plugin; codetalker dropped Cody support after Sourcegraph moved Cody to enterprise-only ($59/user/mo min) in July 2025
- **GitHub Copilot for JetBrains** — uses JetBrains' Copilot plugin; narration via that path is being scoped as part of SP-10's Copilot Chat adapter (covered separately)
