# CodeTalker for Aider

**Status:** Coming in v1.x (SP-10 of the launch master plan).

Aider is a CLI-first AI pair-programming tool. It does not natively support MCP, so codetalker-for-Aider requires a bespoke adapter rather than the universal `codetalker-mcp` server.

## Planned mechanism

A new `codetalker-aider` CLI wrapper (Python console_script) that:

1. Spawns Aider as a subprocess
2. Monitors Aider's stdout for the standard event markers (commit, /run, /shell, file diffs)
3. Pipes those events to the codetalker daemon's narration engine
4. Passes everything else through to the user's terminal transparently

Usage will look like:

```bash
codetalker-aider --model claude-sonnet-4-6 myrepo/
```

Identical to running Aider directly, plus narration.

## Why this approach

Aider doesn't have an event/hook system that exposes "the agent just edited a file" or "the agent just ran a command" as discrete signals. The simplest universal approach is to wrap the CLI and pattern-match on output.

Alternative: monitor Aider's git commits + `.aider.*.log` files. But that gives us less-granular events.

## Timeline

The Aider adapter is part of SP-10 in the launch master plan, scheduled after v1 launch. It's one of the two **Pro Plus** ($3/mo addon) platform integrations along with JetBrains AI Assistant.

If you want to be notified when this lands: watch the [GitHub repo](https://github.com/OpenCircuitDev/codetalker) or subscribe to the launch newsletter at https://codetalker.opencircuit.studio.

## Community workarounds (interim)

A few community-built MCP wrappers for Aider exist (`disler/aider-mcp`, `danielscholl/aider-mcp`). These let MCP-speaking clients drive Aider through MCP tool calls. However, they don't solve the narration problem in the other direction — they let an agent USE Aider, not let Aider's events trigger narration.

If you want narration for Aider TODAY, the manual workaround is:
1. Run `claude-code-talker serve` to start the daemon
2. In a separate terminal: `aider` (or whatever invocation you use)
3. Periodically run `claude-code-talker speak "Aider made an edit"` (or similar) when you want narration

It's not seamless, but it works until v1.x ships the proper adapter.
