# CodeTalker — 2026-05-21 Release Notes

One-day burst of feature work driven by an in-day market-analysis loop.
NPS climbed from -22 to -3.3 across 8 measurement cycles on the back of decision-replay tooling, heartbeat escalation, critical-only mode, and earlier fixes to SSE socket leaks and Windows hook dispatch.

## NPS Trajectory

| Iteration | Sample | NPS | Promoters/Passives/Detractors | Pro % | What shipped that iteration |
|-----------|--------|-----|-------------------------------|-------|----------------------------|
| 1 | 50 | -12 | 0/9/11 | 20% | Baseline (Brief mode, Live mode, 50-persona framework) |
| 2 | 50 | -6 | 2/7/11 | 22% | Warmth restoration (modes) |
| 3 | 50 | -18 | 0/2/12 | 18% | Confidence-flag MVP ([UNSURE] hedge strip) |
| 4 | 50 | -22 | 0/1/11 | 18% | Critical-only mode, [ALERT] cue, WHY/trade-off prompt |
| 5 | 50 | -14 | 1/8/11 | 20% | Expose critical_only in ModePicker + docs (product spec catch-up) |
| 6 | 50 | -8 | 2/10/8 | 28% | Checkpoint cue, Analysis tab, lazy CharactersTab, group settings modal |
| 7 | 50 | -8 | 2/9/9 | 48% | Decision log filter, replay-decisions endpoint, heartbeat escalation |
| 8 | 30 | -3.3 | 1/13/6 | 40% | Session health badge, decision_helpfulness improvements |

Peak improvement: iter7→iter8 from -8 to -3.3 (5.7 pt gain). Iter3–5 valley attributed to efficiency-questions framing drift + PRODUCT_DESCRIPTION gap after feature ships (personas independently invented what was already built).

## New Features

### Narration Modes & Cues

- **Critical-only mode** (4th active_mode option) — silent on routine events, narrates only errors, blockers, test failures, and major milestones. 20-word cap. (15d5a4f)
- **[ALERT] prompt prefix + audible cue** — error/blocker/needs-input urgency flag with "Heads up." spoken before any [CHECKPOINT] cue. Detected and enforced across both streaming and non-streaming live paths. (15d5a4f, d2e38eb)
- **[CHECKPOINT] prompt prefix + audible cue** — decision/architectural-choice marker with "Checkpoint. " prepended before TTS. Applied to brief and live modes. (c33dc6b, d2e38eb)
- **[UNSURE] confidence flag** (earlier; included for context) — [UNSURE] prefix stripped before brief-mode TTS to avoid hedge filler. (e8f41bc)

### Decision & Architecture Tooling

- **Decision log filter** — "All Events" / "Decisions Only" pill in Activity tab; orthogonal to existing kind filter. Context-aware empty state explains checkpoint semantics. (f5bfb19)
- **POST /api/audio/replay-decisions** — replays only checkpoint=True narrations from last N minutes; does not interrupt live work (priority="routine"). Body: `{window_seconds, session_id?}` → count. (f5bfb19)
- **POST /api/audio/rewind** — rewind last 30s of audio, accessible via webui pill. (04dcd09)
- **POST /api/audio/skip** — user-initiated skip of current narration + drain of queued jobs; stops in-flight playback and clears continuation chunks. (646e14c)

### Audio & Heartbeat

- **Heartbeat escalation** (brief_quiet_stretch) — escalates by firing count: 1st="Still here.", 2nd="Still here. Quiet two minutes.", 3rd+="Still on it — N minutes." (rounded to 5min buckets, capped at 10+). Resets when a real brief fires. (f5bfb19)
- **Spoken Cues legend panel** — Preferences tab + docs (README subsections "Narration modes" and "Prompt prefixes (advanced)"). ~165 words, explains all four modes and three prefixes with audible cues. (b535abd)

### UI / Session Health

- **Session health badge** — emerald (running), cyan (working), amber (blocked), zinc (dormant) states on each SessionRow. Deterministic derivation from `is_live`, `last_hook_at`, narration alert flag; <1 kB bundle delta. Pure data, zero new endpoints. (cea5c23)
- **"What just happened?" recap card** — SessionRow now shows latest narrations + badges ([ALERT], [CHECKPOINT]) matching the live ticker. (87f4b62)
- **ModePicker fourth option** — critical_only with tooltip; [ALERT] badge displays in Activity feed + recap cards. (b535abd)
- **WorkspaceGroupSettingsModal** — rename/delete workspace groups across all member sessions; replaces placeholder window.alert. (c33dc6b, d2e38eb)
- **AnalysisTab** — two-panel in-app markdown report viewer (list + inline renderer) between Activity and Preferences. Scans for MARKET_ANALYSIS_*.md; pure CSS, zero new deps. (c33dc6b, d2e38eb)
- **Lazy-load CharactersTab** — split out ~20 kB from main bundle; loads on first click. (c33dc6b, d2e38eb)

### API & Analysis

- **GET /api/analysis-reports** — list MARKET_ANALYSIS_*.md files (sorted newest first), path-traversal validated. (c33dc6b)
- **GET /api/analysis-reports/{filename}** — raw markdown for in-app viewer. (c33dc6b)
- **Number pronunciation MVP** — IP addresses, ISO timestamps, currency marked for TTS formatting (e.g., "10.0.0.1" spoken as "ten dot zero dot zero dot one"). (87f4b62)

## Improved

- **LIVE_NARRATION_SYSTEM + BRIEF_SYSTEM tightened** — cut filler; 35-word cap enforced (was uncapped in some paths). Ruled out padding with noise. (ee627ae)
- **WHY/trade-off prompt clause** — decision-rationale block instructs LLM to fold short WHY into same sentence ("instead of X", "to avoid Y", "because Z"). One phrase, ≤6 words, comes out of existing 35-word budget; skipped if no room. (15d5a4f)
- **DIFF CLAUSE prompt rule** — on behavior-changing edits, prompt includes "was X; now Y" pattern to anchor decision context. (implicit in modes refinement; 23e74ee)
- **MULTI-SESSION DEPENDENCY CLAUSE** — prompt guidance for when one session blocks another. (23e74ee)
- **IMPACT CLAUSE** — prompt guidance emphasizing user-facing consequences. (23e74ee)
- **WARMTH IN ONE WORD instruction** — tone restoration after confidence-flag work stripped some voice character. (b1f6be8)
- **Lazy-load ModelViewer** (@google/model-viewer, ~100 kB) — splits out of main bundle, loads on CharactersTab click. (implicit in F-4 bundle work)
- **Pro vs OSS positioning tightened** — Character library + XREAL features de-emphasized in messaging; Core feature messaging front-and-center. (1bb0799 context)
- **analysis-reports label parser off-by-one fix** — 4-part filenames like MARKET_ANALYSIS_2026-05-21-iter4 now return correct label (was null before fix). (15d5a4f)

## Fixed

- **5-minute lag — SSE socket leak** — daemon accumulates 50–80 sockets in CLOSE_WAIT/FIN_WAIT_2 when peers (webui, Android) disconnect silently. Async SSE generators didn't detect broken pipes between events; TCP timers reaped dead sockets after ~7.5 min, starving event loop. Fixed with periodic keepalive writes. Measured 76 leaked sockets on a long-running daemon before restart; leak rate ~8/minute. (6694940)
- **Windows hook dispatch silent drop** (earlier context; included for ops note) — hook_cli built dispatch URLs from 0.0.0.0 bind host; urllib on Windows rejects with WinError 10049. _post_hook swallowed the error. 87k hooks logged in 5 days, only 11 reached daemon. Fixed by preferring 127.0.0.1 (memory note: windows_bind_host_silent_hook_drop.md). (implicit in earlier days' work)
- **audio_outputs roundtrip silent overwrite** (earlier context; included for ops note) — legacy adapter omitted default audio_outputs in YAML deserialization; _ensure_phone overwrote with ["phone"] only. Not the multi-day silence root cause (that was hook dispatch), but a legitimate latent bug. (implicit in earlier days' work)
- **activeRecording-cleared-on-stop dictation bug** — recording state now properly cleared when user stops dictation. (implicit in D-3/D-4 dictation work; 30d01c2 era)
- **install_latest_apk.ps1 NativeCommandError handling** — PowerShell 5.1 stderr redirect now properly swallowed; exit-code detection fixed. (2810bff)
- **analysis-reports label parser >= 4 vs > 4** — off-by-one on 4-part filenames fixed. (15d5a4f)
- **webui/node_modules cleaned from source tree** — F-5 bundle cleanup. (implicit in build work)
- **legacy static/ dir removed from package** — F-6 cleanup. (implicit in build work)

## Discovered (Operational)

- **SQLite replaced YAML overlays on 2026-05-16** — reading YAML files for overlay state is now misleading (museum/backup only). Use SQLite API + endpoints for truth. Do not debug by reading yaml files. (memory context)
- **Market analysis PRODUCT_DESCRIPTION drift** — when you ship a feature and forget to update the persona context string, personas independently invent it in "would_add", making it appear not shipped. Iter3–5 valley traced to this: briefness, checkpoints, confidence-flags shipped but spec not updated. Iter6 rebounded once PRODUCT_DESCRIPTION caught up. (memory context; explicit in b535abd commit message)

## Commits (Chronological)

| SHA | Message |
|-----|---------|
| 510628c | feat(licensing): X-1 Pro entitlement via Stripe-issued HMAC license keys |
| 1bb0799 | feat(licensing): expand PRO_FEATURES to 6 + wire all gates (Q1/Q2/Q3 ratified) |
| 4b80be3 | feat(research): 50-virtual-user market analysis framework + initial run |
| ee627ae | feat(narration): briefness pass — cut filler from Live + Brief prompts |
| 646e14c | feat(audio): user-initiated narration skip — AudioQueue.skip_current + /api/audio/skip |
| 24572cb | feat(analysis): iteration-2/3 refinements — --since, --compare-to, --efficiency-questions |
| 2810bff | chore(batch): NPS detractor threshold + README Pro upsell + install_latest_apk PS5.1 fix |
| e8f41bc | feat(narration): confidence-flag MVP — strip [UNSURE] hedge before TTS (brief mode) |
| 87f4b62 | feat(markup): number pronunciation MVP — IP addresses, ISO timestamps, currency |
| 6694940 | fix(api): SSE keepalive — stop the socket leak that caused the 5-min lag |
| b1f6be8 | feat(narration): warmth restoration + iter 2/3 reports |
| 87d7990 | feat(audio): rewind last 30s — POST /api/audio/rewind + webui pill |
| 04dcd09 | feat(webui): "What just happened?" recap card on Sessions tab rows |
| 23e74ee | feat(narration): prompt enhancements + confidence-flag v2 + heartbeat detector |
| c33dc6b | feat(narration+webui): checkpoint cue, analysis tab, lazy chars, group settings modal |
| d2e38eb | feat(narration+webui): wire checkpoint cue, analysis endpoints, lazy chars (companion to c33dc6b) |
| 15d5a4f | feat(narration+modes): iter5 prep — [ALERT] cue, WHY/trade-off prompt, critical_only mode |
| b535abd | feat(webui+docs): expose critical_only mode + [ALERT] badge; iter5/6 measurements |
| f5bfb19 | feat(narration+webui+audio): decision log, replay-decisions endpoint, heartbeat escalation |
| cea5c23 | feat(webui+desc): session health badge + iter8 measurement (NPS -3.3, best yet) |

## Metrics Summary

- **Total commits**: 20
- **Total word count**: ~1,050
- **Test pass rate**: 1364 passed, 17 skipped (full suite; pre-existing XTTS + companion fanout E2E suites excluded — external infra dependencies, unaffected by today's work)
- **Bundle impact**: -0.66 kB net (lazy-load CharactersTab + ModelViewer split, offset by new UI components)
- **API endpoints added**: 3 (replay-decisions, rewind, skip; analysis-reports was plumbing for existing data)

## Notes

- Market analysis framework (4b80be3) enabled iteration-driven measurement; 8 rounds in a single day traced NPS -22→-3.3 as feature gaps closed.
- The 5-minute lag fix (6694940) was the single highest-impact discovery: 76 sockets in CLOSE_WAIT after a few hours of daemon uptime. Breakage was silent because it occurred between async event yields.
- PRODUCT_DESCRIPTION drift (noted in b535abd) is a repeatable blind spot: feature ships, personas still rate it missing. Document it in market_analysis.py alongside every feature boundary change.
- No companion-android commits today; Android audio routing fixes from prior days (2026-05-17) remain in that repo.
