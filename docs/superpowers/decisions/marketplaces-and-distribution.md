# Marketplaces + Distribution

**Status**: Drafted 2026-05-21
**Owner**: Brand
**Scope**: Where CodeTalker lists, in what order, with what effort

CodeTalker has three distinct artifacts that each distribute through their
own marketplace ecosystem:

1. **Python daemon** — `claude-code-talker` on PyPI. Free.
2. **Android companion app** — `dev.opencircuit.codetalker`. Pro feature.
3. **XREAL Beam Pro support** — the same Android app via XREAL's Nebula launcher.

Plus the MCP server interface that lets the agent side connect to ~12
AI coding tools.

## Distribution matrix

| Channel | Artifact | Audience | Listing requirements | Revenue cut | Effort | Strategic value |
|---|---|---|---|---|---|---|
| **PyPI** | Python daemon | Dev tools (5M+ monthly) | Free account | None | Low | **5** — shipped; canonical |
| **MCP Registry** | MCP server | AI/code agents; Anthropic-blessed | Namespace verification | None | Low | **5** — canonical discovery |
| **Claude Code plugin marketplace** | MCP surface | Claude Code users (~500k) | Doc submission | None | Medium | **5** — hero use case |
| **Cursor Marketplace** | MCP plugin | Cursor users (~100k); launched Feb 2026 | Plugin submission | TBD (Cursor revenue-share) | Medium | **4** — emerging channel |
| **Homebrew** | Python daemon | macOS devs (millions) | Public tap + PR | None | Medium | **4** — broad CLI reach |
| **Winget** | Python daemon | Windows devs (millions) | Community manifest | None | Medium | **4** — Windows adoption |
| **Google Play Store** | Android app | Pro subscribers (target 100k+) | $25 dev fee, Sept-2026 "verified developer" rule | 20% subscriptions (new installs); 30% existing | Medium | **4** — required for Pro |
| **GitHub Releases** | All artifacts | Power users; direct download | Free hosting | None | Low | **3** — always-on fallback |
| **VS Code Marketplace** | VS Code extension (we don't have one yet) | VS Code users (20M+) | Unique name | None | High | **2** — Continue.dev / Cline already ship MCP, so this is nice-to-have |
| **Zed extension registry** | Zed extension (we don't have one yet) | Zed users (small, growing) | PR to zed-industries/extensions | None | High | **2** — small user base; MCP via Continue is sufficient |
| **Samsung Galaxy Store** | Android app | Samsung device owners (300M+) | Dev account; stricter review | TBD | Medium | **2** — secondary Android reach |
| **Amazon Appstore** | Android app | Fire tablet / Amazon account | Dev account | TBD | Medium | **1** — niche |
| **F-Droid** | Android app | Privacy-conscious users (~1M) | Open source only | None | Low | **1** — incompatible with paid Pro |
| **Aptoide** | Android app | Open-source ecosystem | Manual submission | None | Low | **1** — unvetted; reputational risk |
| **Product Hunt + Hacker News + r/ClaudeAI** | Launch posts | Discovery-driven devs | None | None | Low | **3** — one-shot launch boost |

## Recommended launch sequence

### Phase 1 — at v1.0 ship
1. **PyPI** — already shipped, zero effort.
2. **MCP Registry** — submit daemon with GitHub OAuth + namespace claim (~30 min).
3. **Claude Code plugin marketplace** — verify our existing listing (~10 min).
4. **GitHub Releases** — tag + publish on `vNext` → `main` merge (trivial).
5. **codetalker.opencircuit.studio** — already scaffolded; needs OAuth apps + Stripe live mode to go production.

### Phase 2 — within 2-4 weeks of v1.0
6. **Google Play Store** — Pro tier non-negotiable. Budget developer verification upfront for the Sept 2026 rule.
7. **Homebrew tap** — create `homebrew-codetalker`; ~1-2 hr effort.
8. **Winget community manifest** — ~30 min.
9. **Launch posts** — Product Hunt + Show HN + r/ClaudeAI + r/LocalLLaMA. Coordinated single-day launch.

### Phase 3 — v1.1, deferred until demand justifies
10. **Cursor Marketplace** — wait for the Feb-2026 launch to stabilize, then craft a plugin bundle.
11. **VS Code extension** — only if Continue.dev / Cline's MCP coverage proves insufficient.

### Phase 4 — skip or de-prioritize
- Samsung Galaxy Store: defer until Pro subscriber base grows.
- Amazon Appstore: skip; Fire tablet market too small for our audience.
- F-Droid, Aptoide: skip — incompatible with paid Pro model.

## Key policy gotchas

- **Google Play verified developer** rule lands Sept 2026 — must complete verification before Pro launch on Android.
- **MCP registry namespace** — claim `opencircuit.codetalker` or `codetalker` early; namespace squatting is real.
- **Cursor marketplace** is fresh (Feb 2026 launch); plugin format may change. Watch for v1 of the spec to stabilize.
- **Homebrew Python formula** must declare the right Python version; CodeTalker requires 3.10+.

## Open

- Should we ship a CodeTalker VS Code extension? (Phase 3 decision — defer until we know how many of our target users live in VS Code with no MCP-compatible plugin already.)
- Should the daemon also have a Cargo / npm bridge for non-Python tool surfaces? (Probably not v1; revisit if integrations#13+ requires it.)

Sources: official MCP registry, Google Play service fee schedule, Cursor marketplace docs, Zed extensions guide, Homebrew Python-for-Formula-Authors, F-Droid inclusion policy.
