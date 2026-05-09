# CCT-28 UX Refinement — Investigation

Read-only recon for the three reported symptoms in the Phase 27 React dashboard.
All file:line references are absolute paths under
`core/claude_code_talker/webui/src/` unless otherwise noted.

---

## Symptom: Session name flicker

### Root cause: frontend reverses the backend's title precedence chain

**Backend** (`core/claude_code_talker/api.py:84-99`) resolves `display_name` with
this priority chain:

```
persistent.display_name
  > c.custom_title       (Claude Code /title rename — verbatim)
  > c.vscode_label       (VS Code panel label)
  > slug_display         (kebab slug → Title Case)
  > c.title              (auto-title: ai-title or first user message)
  > c.project_slug
```

The backend ALSO returns the raw `c.title` as a separate field on every session
(api.py:104):

```python
"title": c.title,
"display_name": display_name,
```

**Frontend** (`SessionCard.tsx:21`) reads them in the WRONG order:

```ts
const headline = session.title || session.display_name || session.session_id.slice(0, 8);
```

This means when `c.title` is non-empty (Claude Code has emitted an ai-title or a
first user message has been parsed), the frontend shows that auto-title and
ignores the carefully-resolved `display_name` containing the user's
`/title` rename. The backend's precedence chain is completely overridden.

### Why the flicker

`SessionCatalog.scan()` (`catalog.py:295-344`) is called on a 30-second watcher
loop. `c.title` is **cached** across rescans (`catalog.py:322`:
`prior_titles.get(sid) or _read_transcript_title(transcript)`), but
`custom_title` and `slug` are **always re-read** (line 325).

Sequence that produces flicker:

1. New session lands. First scan can hit a transcript before any ai-title or
   user-message line is written → `c.title = ""`. Frontend falls through:
   `headline = session.display_name` → shows the user's customTitle / slug.
2. Watcher rescans 30s later. Now the transcript has a parseable user message
   line → `c.title = "fix the auth bug"`. Frontend's `session.title` now wins:
   headline becomes "fix the auth bug" — **even if** the user has run `/title`
   to rename it to something else.
3. The user's customTitle is still the displayed `display_name`, so the headline
   visibly flips between two strings depending on which scan lands.

There is also a secondary path: the "live but not in catalog" branch
(`api.py:124-140`) emits **no `title` field** at all. If a session momentarily
toggles between this branch and the catalog branch (e.g. catalog rescan window
race), the `title` field appears and disappears.

### Supporting code

- `SessionCard.tsx:21` — reversed precedence: `session.title || session.display_name`.
- `api.py:92-99` — backend's correct precedence chain (already resolved into `display_name`).
- `api.py:104-105` — backend exposes both `title` and `display_name` separately.
- `api.py:131-134` — live-but-not-cataloged branch omits `title`.
- `catalog.py:322,325` — `title` cached, `custom_title` re-read each scan.
- `SessionCard.tsx:76-80` — subtitle block already special-cases display_name
  diff vs headline, which is dead UI when the precedence is fixed.

### Proposed fix shape

In `SessionCard.tsx`, drop `session.title` from the headline computation
entirely. The backend already resolved precedence; trust it:

```ts
const headline = session.display_name || session.session_id.slice(0, 8);
```

Then remove the now-redundant subtitle block (`SessionCard.tsx:76-80`).
Optionally, drop `title` from the `Session` type (`types.ts:23`) since it
should not be consumed by the UI — only `display_name` is the contract.

Backend is already correct. No changes there.

---

## Symptom: Focus loss during edits

### Root cause: SessionCard re-renders aggressively during background refetches

The actual bug is not unmounting — `SessionGrid.tsx:29` keys cards by
`session_id`, which is stable, so cards don't remount. The bug is **layout
churn while a native `<select>` popup is open closes the popup**, and **brief
data state transitions reset controlled selects**.

### Refetch cadence

| Hook | Interval | What it returns |
|------|----------|-----------------|
| `useSessions` | 2000ms (`useSessions.ts:8`) | `Session[]` |
| `useSessionConfig` | 5000ms (`useSessionConfig.ts:8`) | `SessionConfig` per session |
| `useDaemonHealth` | 5000ms (`useDaemonHealth.ts:8`) | `{ok}` |
| `useNarrationStream` | continuous SSE (`useNarrationStream.ts:9-28`) | event stream |

Default `staleTime` from `App.tsx:14` is `1000ms`. Every 2s the sessions list
returns a NEW array reference, even when the content is identical (the daemon
re-serializes from the catalog, which itself is rescanned on a 30s interval —
but the API serializes on every request).

### Per-render churn that closes open `<select>` popups

1. **`SessionGrid.tsx:23`** — `[...live].sort(...)` creates a fresh sorted
   array on every poll. AnimatePresence's children get a new prop reference,
   but keyed cards do not remount.
2. **`AnimatePresence` reordering** — `last_modified` ticks update reorder the
   children. CSS grid reflow alone is enough to dismiss native select popups
   on Windows.
3. **`ProjectBadge.tsx:11`** — `relativeTime(lastModified)` is computed inline
   on every render using `Date.now()`. On a 2s poll cadence this means every
   card in the grid produces a new "X seconds ago" string each tick.
4. **`SessionControls`** subscribes to `useSessionConfig` independently per
   card, so a 5s poll fires a refetch in addition to the 2s sessions poll —
   any in-progress dropdown interaction lands in the window of one of the two
   refetches with high probability.

### Controlled-select transitions

`ModePicker.tsx:11-22` and `VoicePicker.tsx:23-39` are fully controlled. They
guard against unknown values by injecting an extra `<option value="">…`
when the current value isn't in the option list. If the user opens the
dropdown and the parent re-renders with a different `value` prop (e.g.,
because react-query swapped data references), React reconciles the `<option>`
list — that **doesn't** drop focus by itself, but if the value prop briefly
becomes `undefined` (it shouldn't with default react-query v5 behavior, but
a slow 401/error can cause it), the value resets.

`VoicePicker.tsx:9-17` also uses a separate `useQuery(["voices"])` — voices
have `staleTime: 60_000` so this is fine.

### Supporting code

- `useSessions.ts:5-11` — 2000ms refetch interval, no `staleTime`.
- `useSessionConfig.ts:5-12` — 5000ms refetch interval, no `keepPreviousData`,
  no `staleTime`.
- `App.tsx:13-15` — global `staleTime: 1000` is shorter than any refetch
  interval, so every poll is a real fetch.
- `SessionGrid.tsx:23` — fresh sort on every render.
- `ProjectBadge.tsx:11` — `Date.now()` recomputed in render path.
- `ModePicker.tsx:14-16` — controlled `<select>` with conditional unknown
  option.
- `VoicePicker.tsx:24-37` — same pattern, plus `disabled={isLoading}` flips
  during refetch (but `isLoading` is true only on first load in v5, not on
  refetch — so this should not flip mid-edit).

### Proposed fix shape

1. Bump `useSessions` to 5000ms (or higher) and add
   `placeholderData: keepPreviousData` so the data reference is preserved
   when content is identical. Same for `useSessionConfig`. (Or move to SSE
   for sessions — out of scope for this pass.)
2. Memoize the sorted array in `SessionGrid` and gate it on
   `last_modified` summary or shallow-equal session IDs.
3. Memoize `ProjectBadge` so it only re-renders when `lastModified` changes
   by enough to flip the human-readable bucket.
4. Add `staleTime` >= refetchInterval so cached data doesn't appear stale
   between polls (prevents needless refetches on focus events).
5. Track unsaved edits in `SessionControls` with a `useRef` flag and skip
   passing `config` through during active interaction. This is the heaviest
   fix; consider only after the cheap ones land.
6. Optional: render selects as uncontrolled (`defaultValue` + onChange) and
   reset them only on `key={config-version}` so user edits aren't clobbered
   by background refetches at all.

---

## Symptom: Twitchy re-renders

### Root cause: every poll cascades through every visible component

This is the same root cause as focus loss but observable as visual jitter.
Specific contributors:

1. **`SessionGrid.tsx:23-31`** — sort + map runs every 2s. Each
   `motion.article` re-evaluates its `variants` / `transition` on every
   render. The card itself doesn't animate after mount, but framer-motion
   internally diffs the variants.
2. **`AnimatePresence` reordering without `layout` prop** — when sessions
   reorder by `last_modified`, items snap to new positions instead of animating
   between them. Combined with the 2s poll, any session whose `last_modified`
   ticks shifts everything around it.
3. **`ProjectBadge.tsx:11`** — relative-time string changes every render. On
   a 2s tick, every visible card flickers its timestamp string.
4. **`LiveTicker.tsx:52-82`** — the inner `<ul key={filter}>` has a `key`
   bound to the filter value. Switching filter remounts the entire list,
   re-running enter animations on every event. While correct, this is
   expensive when many events are present. Note: SessionCard's LiveTicker
   block at line 83-87 only renders when `events.length > 0`, but
   **`session.events` is never populated by the backend** (api.py:100-140
   does not emit an `events` field). So the inner LiveTicker in the card
   is dead code today; only `ActivityTab.tsx` runs the LiveTicker and that
   one feeds from the SSE stream.
5. **SpeakingDot** (`SpeakingDot.tsx:7-18`) uses `motion.span` with a
   continuously animating `breathing` variant. This is fine — framer-motion
   runs it on the compositor. But across many cards it adds GPU work.
6. **CharacterAvatar** (`CharacterAvatar.tsx:30-53`) re-runs the spring entry
   variant on every render unless its parent memoizes. With the 2s poll every
   avatar re-evaluates its spring on each parent re-render. Framer-motion
   only re-animates on mount when using `initial`+`animate` strings, so this
   shouldn't visibly re-animate after mount, but the cost is non-zero.

### Supporting code

- `SessionGrid.tsx:23-31` — re-sort + remap on every poll.
- `ProjectBadge.tsx:3-8,11` — relative-time string with `Date.now()` in
  render path.
- `LiveTicker.tsx:52` — `<ul key={filter}>` remounts list on filter change.
- `SessionCard.tsx:24-36` — every render re-creates a className string
  literal and passes new `variants` reference to motion.
- `SessionCard.tsx:83-87` + `types.ts:35` — `session.events` field declared
  but never set by backend; the inner LiveTicker is unreachable in practice.
- `useNarrationStream.ts:14-22` — SSE handler does an immutable spread on
  every event, then trims. With many events per second the rail re-renders
  on every event. Acceptable for now but worth knowing.

### Proposed fix shape

1. `React.memo(SessionCard)` with a custom comparator on `(session_id,
   display_name, project_slug, last_modified, attached_profile,
   is_speaking, attached_character, mode, is_muted)`. This prevents a card
   from re-rendering when only the list reference changed.
2. Memoize `ProjectBadge` and bucket the relative-time string by minute
   (don't recompute every render — only when `lastModified` crosses a
   bucket boundary).
3. Either remove the dead LiveTicker block from `SessionCard.tsx:83-87`
   (and the `events` field from `types.ts`) OR wire it up to a real
   per-session SSE feed. Today it ships unused code.
4. Stabilize sort: `useMemo(() => [...live].sort(...), [live])` in
   `SessionGrid` once react-query returns a stable reference (see
   focus-loss fix #1).
5. Add `layout` prop to the `motion.article` in `SessionCard` so reorders
   animate between positions instead of snapping.

---

## Other rough edges noticed

- **`SessionGrid.tsx:27`** — `<AnimatePresence>` without `mode="popLayout"`
  or `mode="wait"`. With grid layout this means exiting cards continue to
  occupy a slot during their exit animation. Cosmetic, not a bug.
- **`useNarrationStream.ts:9-28`** — `EventSource` reconnect path
  (`onerror`) is empty. EventSource auto-reconnects on most failures, but
  network errors during dev cause the buffer to grow up to `MAX_BUFFER=50`
  forever. Acceptable.
- **`ActivityTab.tsx:18-39`** — opens its own `EventSource` instead of
  reusing `useNarrationStream`. So when the user is on the Activity tab,
  the daemon receives two SSE subscriptions per page. Minor; consolidate
  on `useNarrationStream` and let ActivityTab adapt the events into
  TickerEvents in a `useMemo`.
- **`api.py:124-140`** — live-but-not-cataloged sessions emit no `title`,
  no `mode`, no `events`. The catalog branch also emits no `mode` /
  `is_speaking` / `is_muted` / `events`. Frontend `types.ts` declares all
  of these as optional but they are universally absent. Either populate
  them backend-side or strip from the type.
- **`SessionCard.tsx:18`** — `muted` is computed from THREE sources
  (`config.enabled`, `session.enabled`, `session.is_muted`) and the
  fallback chain may disagree. If config is loading and session.enabled
  is true and is_muted is false, `muted` is false. Once config loads with
  `enabled: false`, the card flips to muted styling. This will visibly
  flicker on first load. Consider showing a neutral state until config
  resolves.
- **`SessionControls.tsx:12-52`** — the mutation invalidates
  `["session-config", sessionId]`, which schedules a refetch. While the
  refetch is in flight, the dropdown the user just used may briefly show
  stale state. Adding `optimisticUpdate` via `onMutate` would feel
  snappier.
- **`App.tsx:14`** — `retry: false` on every query is fine for dev but
  in production a transient daemon hiccup will produce immediate error
  states. Consider `retry: 1` with a small delay.
- **`ProjectBadge.tsx:11`** — pluralization bug at the boundary:
  `"${Math.floor(sec)} second${sec < 1.5 ? "" : "s"} ago"`. At
  `sec = 0` you get `"0 second ago"` (correct: "0 seconds"). Minor.
- **`useSessionConfig.ts:11`** — `enabled: Boolean(sessionId)` is fine
  since session_id is always present, but if it ever becomes empty
  string the query would silently disable. Defensive code that never
  triggers.

---

## Recommended fix order

1. **Headline precedence (Symptom 1)** — one-line change in
   `SessionCard.tsx:21`. Highest impact, lowest risk. Land first; it
   resolves the worst-feeling symptom and unblocks user testing the
   other fixes.
2. **Memoize `SessionCard` and `ProjectBadge`** — prevents most
   re-renders, mitigates twitchiness without changing fetch cadence.
3. **`placeholderData: keepPreviousData` + raise refetch intervals** —
   reduces the volume of cascading re-renders. Preserves data
   reference equality so the memos in step 2 actually fire.
4. **Memoize sorted array in `SessionGrid`** — depends on step 3 (needs
   stable reference) and step 1 (so headline doesn't depend on `title`
   field flipping).
5. **Remove dead LiveTicker block in SessionCard / drop `events`
   from types** — easy cleanup once symptoms are stable.
6. **Add `layout` prop to `motion.article`** — cosmetic polish,
   defer until the noisy reorders are tamed.
7. **Optional optimistic updates in `SessionControls`** — nice-to-have
   for snappy feel; do after the above stabilize.

Dependencies:
- Step 4 depends on step 3 (stable refs make memo viable).
- Step 2 also depends on step 3 (otherwise memo always misses).
- Step 1 is independent and should ship first.

---

## Files to modify

| File | Lines | Change |
|------|-------|--------|
| `webui/src/components/SessionCard.tsx` | 21 | Drop `session.title` from headline. Use `session.display_name || session.session_id.slice(0,8)`. |
| `webui/src/components/SessionCard.tsx` | 76-80 | Remove or repurpose subtitle block (now dead). |
| `webui/src/components/SessionCard.tsx` | 83-87 | Remove dead LiveTicker block (events never populated) OR wire it up. |
| `webui/src/components/SessionCard.tsx` | 16-93 | Wrap export with `React.memo` + custom comparator. |
| `webui/src/components/SessionGrid.tsx` | 23 | Wrap sort in `useMemo`. |
| `webui/src/components/SessionGrid.tsx` | 27-31 | Optionally add `mode="popLayout"` to `<AnimatePresence>`. |
| `webui/src/components/ProjectBadge.tsx` | 1-19 | Memoize component; bucket relativeTime by minute (or run via setInterval at coarser cadence). |
| `webui/src/hooks/useSessions.ts` | 5-11 | Add `placeholderData: keepPreviousData`, bump `refetchInterval` to ~5000ms, set `staleTime: 4000`. |
| `webui/src/hooks/useSessionConfig.ts` | 5-12 | Add `placeholderData: keepPreviousData`, set `staleTime: 4000`. |
| `webui/src/types.ts` | 23, 35 | Remove `title?` and `events?` from `Session` (or keep with comments noting they are unused). |
| `webui/src/components/SessionControls.tsx` | 14-17 | Optional: add `onMutate` optimistic update for snappier feel. |
| `webui/src/features/activity/ActivityTab.tsx` | 18-39 | Optional: replace bespoke EventSource with `useNarrationStream`. |
| `webui/src/App.tsx` | 13-15 | Optional: bump `staleTime` global default to 4000. |

No backend changes needed for any of the three reported symptoms.

---

## Test strategy

### Existing vitest tests that need updating

- **`__tests__/SessionCard.test.tsx:60-64`** — the test "renders identity zone
  with title and cwd when attached_character present" deliberately sets
  `title: "fix auth bug"` and asserts the title shows. After the fix this
  assertion must change — the fixture should set `display_name: "fix auth
  bug"` and assert that. The test name should also be renamed to reflect
  display_name, not title.
- **`__tests__/SessionCard.test.tsx:77-80`** — "renders ticker when events
  present" — if the dead LiveTicker block is removed, this test must be
  removed too. If kept, the test stays; either way decide before shipping.
- **`__tests__/useSessions.test.tsx:34`** — assertion uses `toEqual` against
  the fixture. After adding `placeholderData: keepPreviousData`, this
  semantic stays the same on first fetch but the test should also assert
  reference stability across two refetches. Add a second case.

### New tests to add

- **`SessionCard.test.tsx`** — assert that when both `title` (from server)
  and `display_name` differ, `display_name` wins. Add fixture with
  `title: "first user prompt that is long"`,
  `display_name: "Fix Auth Bug"` and assert "Fix Auth Bug" renders, the
  long string does not.
- **`SessionCard.test.tsx`** — assert `React.memo` skips re-renders. Render,
  rerender with the same `session` prop (shallow-equal fields), spy on a
  child component (e.g., `ProjectBadge`) — child should not re-render.
  Use `vi.fn()` wrapped component.
- **`SessionGrid.test.tsx` (new)** — render with two sessions, simulate
  `useSessions` returning two consecutive identical-content payloads, assert
  the sorted array reference is stable and `SessionCard` rendered twice
  total (not four).
- **`ProjectBadge.test.tsx` (new)** — assert relative-time bucketing: at
  `lastModified = now - 30s` shows seconds, at `now - 90s` shows
  "1 minutes ago", and crossing the boundary causes one rerender, not many.
- **Integration / focus** — render `<SessionsPane>` with a mocked
  `useSessions` that fires every 100ms, focus a `<select>` inside a
  `SessionControls`, advance fake timers, assert
  `document.activeElement` stays on the select. (This is the canonical
  regression test for the focus-loss symptom.)
- **`useSessions.test.tsx`** — assert `placeholderData` keeps the previous
  data reference between refetches when content is identical (use
  `Object.is` on consecutive `result.current.data` values).

### Manual verification (out of scope for vitest)

- Open the dashboard with five live sessions, click into a `<select>`, wait
  10 seconds, confirm the popup stays open.
- Run `/title my-cool-session` inside Claude Code, confirm the headline
  flips from auto-title to "my-cool-session" within one rescan and stays
  there.
- Watch the grid for 60 seconds with no narration activity, confirm no
  visible jitter (besides the relative-time bucket transitions).
