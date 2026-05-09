# CCT-30 — Open-Core Edition Strategy

**Status:** locked decisions captured 2026-05-09; full spec to be expanded after current UX work completes.

## Decisions locked in

- **Two-repo open-core structure** (option A from brainstorm).
  - Public: `OpenCircuitDev/codetalker` — MIT, everything-except-character-system.
  - Private: `OpenCircuitDev/codetalker-pro` — proprietary, full character system.
- **OSS scope**: TTS daemon, modes (direct/brief/live/trigger), profiles, triggers/tags, voice library, secrets store, sessions, catalog, markup awareness, web UI shell (Sessions/Markup/Activity/Preferences tabs), Claude Code plugin, VS Code extension, Marketplace listing.
- **Paid scope (the character system)**: Phase 25a `characters.py` + CharacterStore + attach lifecycle + cfg merge layer; Phase 25b `mesh/` package + 3D provider adapters + MeshJobTracker + 5 mesh REST endpoints; Phase 25c `voice/cloning_jobs.py` + clone-voice REST + React `features/characters/` (Characters tab, wizard, BrowserRecorder, MeshGenerator, CharacterAvatar — though CharacterAvatar may also serve a future "guest avatar" feature in OSS).

## Architecture: extension points

The OSS core needs three plug-in surfaces so `codetalker-pro` can register without forking:

1. **REST routes**: `register_routes(prefix, routes)` callable that pro packages invoke at startup. Today api.py builds a flat list — refactor to expose a registry. Pro registers `/api/characters/*`, `/api/mesh-jobs/*`, `/api/voice-clone-jobs/*`.
2. **Cfg resolution layer**: `register_cfg_layer(name, resolver)` so the character-identity merge step (between profile and overlay) becomes a registered layer rather than a hardcoded line in `config.resolve_for_session`. Pro registers the character layer.
3. **Web UI tab manifest**: a tab manifest API the React shell reads at startup (e.g., `GET /api/ui/extensions`) listing additional tabs to mount. Pro ships its built JS as a bundle the OSS shell loads dynamically. Alternative simpler path: pro publishes its own React build that imports OSS components; users install the pro npm package separately.

## Open follow-up questions

These don't block locking in A but need answers before drafting the implementation spec:

- **License model for paid**: commercial source-available (e.g., FSL, BSL with eventual MIT conversion)? Closed-source proprietary? Annual subscription vs perpetual license?
- **License verification**: online check at daemon startup with offline grace period? Hardware-keyed? Honor system (just a license file)?
- **Distribution channel**: Gumroad / Stripe / GitHub Sponsors / custom checkout? Self-serve or invoice?
- **Pricing**: one-time? Annual? Per-character / per-mesh-job metered?
- **Trial / demo path**: free OSS + first 1 character + first 5 mesh jobs free in pro? Fully gated?
- **OSS user discovery of paid**: README upsell section? "Upgrade to Pro" link in the dashboard? Standalone landing page?
- **Migration story**: existing users (post-Phase-25a/b/c) who already have characters on disk — do they need to install pro to keep using them, or does OSS render existing characters read-only?

## Implementation phasing (sketch)

1. **Refactor pass on OSS core** — introduce the three extension points above without removing existing functionality. Backward-compatible.
2. **Cleave character system out** — copy `characters.py`, `mesh/`, `voice/`, React `features/characters/` to a new `codetalker-pro` private repo. OSS retains a "characters not installed" empty-state path.
3. **Public release of OSS** — push public repo, announce, list in Claude Code marketplace.
4. **Pro package shape** — pip `codetalker-pro` package + npm `@codetalker/pro-webui` package + license verification.
5. **Distribution + checkout** — pick one of the channels above and ship the upgrade flow.

This sketch is intentionally rough; see "Open follow-up questions" for the gates that turn it into a real implementation plan.
