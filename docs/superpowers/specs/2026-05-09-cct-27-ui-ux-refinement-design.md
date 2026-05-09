# CCT Phase 27 — UI/UX Refinement with Specialist Feedback

**Status**: approved 2026-05-09 (autonomous overnight build, runs after 25b/25c/26), awaiting user verification.
**Scope**: dashboard polish — animation, layered surface palette, layout refinement, character avatars, narration feed restructure, top-level tab navigation.
**Reference**: parent roadmap entry in [2026-05-08-cct-v1-design.md](./2026-05-08-cct-v1-design.md).

## Context

After 25b (3D APIs), 25c (voice cloning UX), and 26 (markup awareness) ship, the system has full functionality but the dashboard feels utilitarian. The user wants something **more fun and engaging** that celebrates the live-data nature of CCT. Phase 27 adds motion, palette, character presence, and information hierarchy improvements drawing on three specialist perspectives.

## Decisions locked in (synthesized from specialist input)

- **Visual / motion**: framer-motion for entry/exit animations; CSS keyframes for breathing speaking-state; `prefers-reduced-motion` respected throughout.
- **Layered surface palette** with CSS custom properties for future light-mode.
- **Information architecture**: 4-zone SessionCard (identity / chips / live ticker / controls); resizable right-panel narration feed; top-level tab navigation.
- **Engagement**: speaking-state breathing, character avatar emergence, persona-reflective card styling, opt-in sound effects with localStorage persistence.
- **Accessibility**: WCAG AA contrast, keyboard nav, focus rings, reduced-motion support.

## Architecture

```
core/claude_code_talker/webui/src/
├── App.tsx                                  # MODIFY — top tab nav (Sessions / Characters / Markup / Activity)
├── index.css                                # MODIFY — CSS custom properties + Tailwind v4 @theme tokens
├── components/
│   ├── primitives/
│   │   ├── Chip.tsx                         # NEW — colored badge
│   │   ├── LiveDot.tsx                      # NEW — pulsing status dot
│   │   ├── Avatar.tsx                       # NEW — character avatar (letter-glyph or rendered)
│   │   ├── SpeakingPulse.tsx                # NEW — breathing animation wrapper
│   │   ├── AnimatedRow.tsx                  # NEW — framer-motion entry/exit
│   │   └── ConfirmDialog.tsx                # NEW (or shared with 25c)
│   ├── SessionCard.tsx                      # REWRITE — 4-zone layout
│   ├── SessionGrid.tsx                      # MODIFY — pass character data
│   ├── NarrationFeed.tsx                    # SPLIT — see below
│   ├── narration/
│   │   ├── NarrationFeedPanel.tsx           # NEW — resizable shell
│   │   ├── NarrationFilters.tsx             # NEW — status chips + session pill
│   │   └── NarrationRow.tsx                 # NEW — animated entry
│   ├── GlobalStatusBar.tsx                  # MODIFY — top tab strip + uptime tooltip
│   ├── Markup.tsx                           # NEW — frequency-grouped accordion (Phase 26 surfaces here)
│   ├── Activity.tsx                         # NEW — recent narrations + 3D job status (Phase 25b surfaces here)
│   └── PreferencesPanel.tsx                 # NEW — sound effects + reduced-motion override
├── hooks/
│   ├── usePrefs.ts                          # NEW — localStorage-backed preferences
│   └── useReducedMotion.ts                  # NEW — wraps framer-motion's hook
└── __tests__/
    ├── primitives/Chip.test.tsx
    ├── primitives/LiveDot.test.tsx
    ├── primitives/Avatar.test.tsx
    ├── primitives/SpeakingPulse.test.tsx
    ├── SessionCard.test.tsx (UPDATED)
    ├── NarrationFeedPanel.test.tsx
    ├── GlobalStatusBar.test.tsx (UPDATED)
    └── usePrefs.test.tsx
```

New dependencies: `framer-motion` (~30KB gzip), `react-resizable-panels` (already in package.json from Phase 17 scaffold but unused).

## Section 1 — Color palette + token system

CSS custom properties in `index.css`, exposed as Tailwind v4 `@theme` tokens:

```css
@theme {
  --color-surface-0: #0a0b10;        /* page bg */
  --color-surface-1: #11141c;        /* header, feed */
  --color-surface-2: #171b26;        /* cards */
  --color-surface-3: #1f2433;        /* hover/active */
  --color-border-subtle: #252b3a;
  --color-border-strong: #363d52;

  --color-text-primary: #e6e8ef;
  --color-text-secondary: #a7adbe;
  --color-text-tertiary: #6c7388;

  --color-accent-live: #34d399;       /* audible/speaking */
  --color-accent-live-deep: #10b981;
  --color-accent-muted: #fb7185;      /* muted/error */
  --color-accent-activity: #a78bfa;   /* queued/processing */
  --color-accent-warning: #fbbf24;    /* overflow */
  --color-accent-brand: #22d3ee;      /* focus/wordmark */
}
```

All accent-on-surface combinations verified WCAG AA 4.5:1 for body text.

## Section 2 — SessionCard 4-zone rewrite

Current SessionCard puts display_name middle-of-card with low visual weight. New layout:

```
┌─────────────────────────────────────┐ ← border-l-4 (live=emerald, muted=rose)
│ [Avatar]  Display Name              │ Zone 1: Identity
│           project_slug · 14s ago    │
│ ─────────────────────────────       │
│ [profile] [mode] [voice] [muted?]   │ Zone 2: State chips
│ ─────────────────────────────       │
│ "I'm restarting PIE clean..."  ●    │ Zone 3: Live ticker (last 1-2 narrations)
│ ─────────────────────────────       │
│ [mute] [direct ▾] [voice ▾]         │ Zone 4: Controls (semi-transparent until hover)
└─────────────────────────────────────┘
```

- **Zone 1 (Identity)**: avatar (32px circle, persona-colored letter-glyph or rendered character image), display_name `text-base font-medium`, project slug + relative time `text-sm text-secondary`
- **Zone 2 (State chips)**: profile chip + mode chip + voice glyph + mute indicator. Uniform chip height. Persona-color subtle accent under display name.
- **Zone 3 (Live ticker)**: last 1-2 narrations from this session via `useNarrationStream(session.session_id)`. Status dot, truncated text. Collapses gracefully when no events.
- **Zone 4 (Controls)**: opacity-60 default, opacity-100 on hover. Reduces visual noise when not interacting.

When card is `is_speaking==true`: breathing pulse on inner ring + 3-bar equalizer glyph in identity strip.

## Section 3 — Narration feed restructure

Move from bottom strip to **resizable right panel** using `react-resizable-panels` (default 320px wide on lg+, collapses on md-).

```
┌─────────────┬───────────────┐
│             │ NarrationFeed │
│ Session     │ ─────────────  │
│ Grid        │ [filter chips]│
│             │ ─────────────  │
│             │ [event rows]  │
│             │ ...           │
└─────────────┴───────────────┘
```

Components:
- `NarrationFeedPanel`: resizable shell + state filters
- `NarrationFilters`: button group `All | Speaking | Skipped | Overflow` with counts; per-session filter pill activated by clicking a SessionCard
- `NarrationRow`: animated via framer-motion `AnimatePresence` mode="popLayout" with 200ms slide-in from above + brief color pulse on `speaking` events
- Timestamps in `HH:MM:SS` with `tabular-nums`

## Section 4 — Top tab navigation

`GlobalStatusBar` evolves into `<header>` with:

- Left: codetalker wordmark (cyan accent) + daemon health LiveDot (uptime tooltip on 3s hover)
- Middle: tab strip `Sessions | Characters | Markup | Activity` with focus rings + keyboard nav (arrow keys)
- Right: live session count + Preferences gear

Tab content swaps via `useState<'sessions' | 'characters' | 'markup' | 'activity'>` (no URL routing yet — keeps the change surgical; URL routing arrives later if needed).

## Section 5 — Animation primitives

```tsx
// SpeakingPulse — wraps a child, animates breathing while active
<SpeakingPulse active={isSpeaking}>
  <SessionCard ... />
</SpeakingPulse>

// AnimatedRow — wraps narration feed events with enter/exit
<AnimatedRow key={event.id}>
  <NarrationRow event={event} />
</AnimatedRow>
```

`useReducedMotion` short-circuits both — wraps framer-motion's hook with a `usePrefs()` override path. CSS `@keyframes` for the speaking-pulse breathing (cheap, always-on for many sessions). Animations target `transform`/`opacity` only (composited).

## Section 6 — Character avatars

`<Avatar character={character} size={32}>` renders:
- If `character.mesh_path` set + browser supports `<model-viewer>`: small canvas-rendered preview (loaded lazily on hover)
- Else: persona-colored circle with letter-glyph (first letter of display_name, font-bold, contrast-checked)
- Fallback: generic person silhouette

When 25b finishes a mesh job: avatar morphs from glyph to rendered with 600ms soft-flip (rotate-y, framer-motion `AnimatePresence`).

## Section 7 — Persona-reflective card styling

Each persona has metadata in `personaColors.ts` (from 25c):

```ts
{ methodical: { accent: 'slate-300', font_role: 'sans' },
  warm:       { accent: 'amber-300', font_role: 'serif' },
  technical:  { accent: 'cyan-300',  font_role: 'mono' },
  ... }
```

When a SessionCard has an attached character, its identity strip subtly shifts:
- 2px accent under display_name in character's accent color
- Character name uses character's font role
- Falls back gracefully if no character attached

## Section 8 — Preferences panel

`<PreferencesPanel>` opens from a gear icon in GlobalStatusBar. Backed by `usePrefs()` (localStorage):

```ts
{
  soundEffects: {
    narrationStart: false,    // chime when narration starts
    characterAttached: false, // chime when character attached
    meshReady: false,         // chime when 3D job completes
    daemonError: true,        // default ON for errors
  },
  reducedMotion: 'auto' | 'always' | 'never',  // 'auto' uses prefers-reduced-motion
}
```

Sound effects implemented via Web Audio API (sine-decay envelopes; no asset files). Persisted in localStorage. Default all sound off (TTS already provides plenty of audio).

## Section 9 — Markup tab (Phase 26 surface)

Frequency-grouped accordion replacing flat list:

- **Most active (last hour)**: recognizers that fired recently
- **Frequent**: fired in last day
- **Rare**: fired this week
- **Inactive**: never fired

Each row shows: name, last-fired timestamp, fire count (last hour / last day), test pattern button. Inactive rows collapsed by default.

Pulls data from a new `/api/markup/stats` endpoint (defer to Phase 26 if not present; Phase 27 stub it).

## Section 10 — Activity tab

Combines recent narrations + 3D job status into a single feed:
- Live narration events (last 50)
- 3D mesh job status (queued/running/done) for any character
- Daemon errors and warnings
- Sortable by time

Builds on `/api/narration-stream` (existing) + `/api/mesh-jobs` (Phase 25b).

## Section 11 — Tests (~14 new + ~6 updated)

**New**:
- `Chip.test.tsx`, `LiveDot.test.tsx`, `Avatar.test.tsx`, `SpeakingPulse.test.tsx` (primitive renders + tone props)
- `NarrationFeedPanel.test.tsx`, `NarrationFilters.test.tsx`, `NarrationRow.test.tsx`
- `Markup.test.tsx`, `Activity.test.tsx` (placeholder/stub data)
- `usePrefs.test.tsx`, `useReducedMotion.test.tsx`

**Updated**:
- `SessionCard.test.tsx` — 4-zone structure, persona accent, live ticker
- `GlobalStatusBar.test.tsx` — top tab strip, uptime tooltip, tab keyboard nav

Snapshot tests for static structure (Chip, LiveDot, NarrationRow). Behavioral tests via `getByRole`/`getByText`. `prefers-reduced-motion` mocked via `matchMedia`.

## Section 12 — Implementation phases (12 TDD tasks)

1. **Token system + index.css rewrite** — CSS custom properties + Tailwind @theme + computed-style assertions
2. **Add framer-motion + react-resizable-panels deps** — npm install + smoke build
3. **Primitives: Chip, LiveDot, Avatar** — render tests + snapshots
4. **SpeakingPulse + useReducedMotion** — animation primitives with motion-safe handling
5. **SessionCard 4-zone rewrite** — preserve existing tests; add zone tests
6. **NarrationFeedPanel + NarrationFilters + NarrationRow** — resizable shell + filter chips + animated rows
7. **AnimatedRow with framer-motion** — narration feed entry animation
8. **Top tab nav in GlobalStatusBar** — tab strip + keyboard nav
9. **Characters tab routing** (placeholder if 25c content not present yet)
10. **Markup tab accordion** (Phase 26 surface)
11. **Activity tab** (combines narration + mesh job status)
12. **PreferencesPanel + usePrefs + sound effects + uptime tooltip**

Tasks 1–4 establish foundations. 5/6/8 parallelizable. 7 depends on 6. 9/10/11 each independent (with stub fallbacks if upstream phases unfinished). 12 closes the loop.

## Risks / open questions

- **Performance with many speaking sessions**: animate `transform`/`opacity` only (composited), cap pulse to `is_speaking==true`. Test on 20 simultaneous-narration scenario.
- **Motion sensitivity / accessibility**: `prefers-reduced-motion` honored throughout; manual override in `usePrefs`; keyboard focus always visible.
- **Color contrast**: every accent-on-surface combo verified WCAG AA in token-system task. Document waivers for chips at AA Large 3:1.
- **framer-motion bundle weight**: ~30KB gzip; tree-shake via `framer-motion/m`; consider dynamic-importing Characters/Markup/Activity tabs.
- **`<model-viewer>` browser compat**: graceful fallback to letter-glyph if not supported.
- **Sound effect default-off**: ensure no surprise audio. Document in PreferencesPanel that all sound is off by default.

## Out of scope (deferred)

- Full URL routing (`react-router`) — `useState` tabs are enough for v1
- Light mode (token system enables it; not built in 27)
- Internationalization
- Konami code easter eggs (mentioned in specialist input — defer to 27.1 polish phase)
- Mesh job cost confirm dialogs (Phase 25b's UI)
- Dashboard mobile/responsive optimization beyond what Tailwind provides

## Verification

1. `npm test` — all updated + new vitest tests pass (~50 total)
2. `npm run build` — no TS errors; bundle size reported
3. `pytest core/tests/` — backend untouched; all green
4. Manual: open `/ui-react/` with multiple live sessions; verify breathing on speaking cards, smooth narration entry, tab keyboard nav, reduced-motion honored
5. Manual: lighthouse accessibility audit ≥ 95
6. Manual: enable a sound effect in preferences; verify it plays and persists across reload

## Success criteria

The dashboard feels alive — narrations flow in with motion, speaking sessions visibly pulse, characters carry visual identity, the feed is filterable and resizable. All while respecting accessibility (reduced motion, contrast, keyboard nav). New users notice the polish; existing users find their workflow easier, not interrupted.
