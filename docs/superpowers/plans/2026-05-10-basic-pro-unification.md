# Basic + Pro Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the codetalker Basic webui dashboard and the Pro Android companion app so they share session organization, output routing, active-state flash, workspace grouping, and auto-mode switching — driven through a single daemon state.

**Architecture:** All cross-surface state lives in the daemon. Both clients read `/api/sessions` (webui) or `/api/companion/sessions` (Pro Android), write via `PUT /api/sessions/{id}/overlay`. Persistent_sessions is the source of truth for cross-restart and cross-surface visibility. Audio worker routes per-session via `output_destination`. Hook handlers bump `last_user_interaction_at` so the auto-mode evaluator can switch between brief and live.

**Tech Stack:** Python 3.13 + Starlette (daemon); Kotlin + Compose + Media3 + DataStore (Pro Android); React + TypeScript + Vite + Tailwind + react-query + framer-motion (webui).

**Spec:** `docs/superpowers/specs/2026-05-10-basic-pro-unification-design.md`

---

## File Structure

### Daemon (Python)

- `core/claude_code_talker/api.py` — extend `_merge_into_persistent` for `output_destination` + `auto_mode_enabled` + `auto_mode_idle_threshold_secs`; expose `workspace_group` + `auto_mode_enabled` in `list_sessions` response.
- `core/claude_code_talker/companion/api.py` — expose `is_speaking` + `auto_mode_enabled` in the companion `list_sessions` response.
- `core/claude_code_talker/audio.py` — add per-job `output_destination` resolution; the worker honors it before deciding to play locally / publish to hub / both / skip.
- `core/claude_code_talker/sessions.py` — add transient `is_speaking`, `last_user_interaction_at`, `last_manual_mode_change_at` fields on the in-memory session; add `evaluate_auto_mode(state, sid)` helper.
- `core/claude_code_talker/hook_cli.py` — bump `last_user_interaction_at` on `UserPromptSubmit` hooks; invoke `evaluate_auto_mode` at end of every hook handler that affects a known session.

### Pro Android (Kotlin)

- `companion-android/app/src/main/kotlin/dev/opencircuit/codetalker/net/DaemonClient.kt` — extend `SessionLite` with `isSpeaking`, `autoModeEnabled`, `outputDestination`; add `setOutputDestination()`, `setAutoMode()` helpers.
- `companion-android/app/src/main/kotlin/dev/opencircuit/codetalker/ui/SessionDetailScreen.kt` — append a Destination picker + Auto-mode switch to the Settings panel.
- `companion-android/app/src/main/kotlin/dev/opencircuit/codetalker/ui/SessionListScreen.kt` — flash logic uses `isSpeaking || isRecentlyActive`; auto-ribbon on mode quick-pick when autoModeEnabled.

### Webui (React/TypeScript)

- `core/claude_code_talker/webui/src/types.ts` — extend `Session` + `SessionConfig` interfaces with new fields.
- `core/claude_code_talker/webui/src/components/FilterChips.tsx` — NEW: Live / All / Dormant / Active pills.
- `core/claude_code_talker/webui/src/components/WorkspaceGroupSection.tsx` — NEW: sticky header + collapse + row list.
- `core/claude_code_talker/webui/src/components/SessionRow.tsx` — NEW: compact card matching the Pro Android row.
- `core/claude_code_talker/webui/src/components/SessionDetailPanel.tsx` — NEW: panel-by-panel detail (Name & workspace / Mode / Voice / Cadence / Muted / Destination / Auto-mode / Character read-only).
- `core/claude_code_talker/webui/src/components/SessionGrid.tsx` — rewrite as a filter-chip-driven, grouped, row-list view (was a flat live grid).
- `core/claude_code_talker/webui/src/components/PreferencesPanel.tsx` — add Global Output Destination + Companion Suppress Desktop toggle.
- `core/claude_code_talker/webui/src/features/characters/CharactersTab.tsx` — add Pro badge + migration note.
- `core/claude_code_talker/webui/src/hooks/useSessions.ts` — no shape change, just consume new fields.

---

## Phase A — Daemon Foundation

### Task A1: Persistent overlay recognizes `output_destination`

**Files:**
- Modify: `core/claude_code_talker/api.py` (function `_merge_into_persistent`)

- [ ] **Step 1: Add `output_destination` branch**

In `_merge_into_persistent`, between the `workspace_group` and `display_name` branches:

```python
elif key == "output_destination":
    # v0.1.0 unification — per-session audio routing.
    # Values: "desktop" | "companion" | "both" | "none". Empty/null clears.
    if value is None or value == "":
        existing.pop("output_destination", None)
    else:
        v = str(value).lower()
        if v not in ("desktop", "companion", "both", "none"):
            continue
        existing["output_destination"] = v
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/api.py
git commit -m "daemon: accept output_destination in persistent overlay merge"
```

### Task A2: Persistent overlay recognizes `auto_mode_enabled` + threshold

**Files:**
- Modify: `core/claude_code_talker/api.py` (function `_merge_into_persistent`)

- [ ] **Step 1: Add two branches after `output_destination`**

```python
elif key == "auto_mode_enabled":
    existing["auto_mode_enabled"] = bool(value)
elif key == "auto_mode_idle_threshold_secs":
    if value is None:
        existing.pop("auto_mode_idle_threshold_secs", None)
    else:
        try:
            existing["auto_mode_idle_threshold_secs"] = float(value)
        except (TypeError, ValueError):
            continue
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/api.py
git commit -m "daemon: accept auto_mode_enabled + threshold in persistent overlay merge"
```

### Task A3: Expose `is_speaking` + `auto_mode_enabled` on companion endpoint

**Files:**
- Modify: `core/claude_code_talker/companion/api.py` (function `_row` inside `list_sessions`)

- [ ] **Step 1: Pull `is_speaking` from live session + persistent overlay flag**

Inside `_row`, after `enabled = ...`, add:

```python
is_speaking = bool(getattr(live_match, "is_speaking", False)) if live_match else False
auto_mode_enabled = (
    persistent.get("auto_mode_enabled", False) if persistent else False
)
output_destination = (
    persistent.get("output_destination") if persistent else None
)
```

And in the returned dict, add the three fields:

```python
return {
    ...,
    "is_speaking": is_speaking,
    "auto_mode_enabled": auto_mode_enabled,
    "output_destination": output_destination,
    ...,
}
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/companion/api.py
git commit -m "daemon: expose is_speaking + auto_mode_enabled + output_destination on companion endpoint"
```

### Task A4: Expose `workspace_group` + `auto_mode_enabled` + `output_destination` on broader `/api/sessions`

**Files:**
- Modify: `core/claude_code_talker/api.py` (function `list_sessions` near line 100)

- [ ] **Step 1: Pull from persistent overlay + add to merged dict**

Where the existing `merged.append({...})` block lives, add:

```python
"workspace_group": (persistent.get("workspace_group") if persistent else None),
"auto_mode_enabled": (persistent.get("auto_mode_enabled", False) if persistent else False),
"output_destination": (persistent.get("output_destination") if persistent else None),
"is_speaking": bool(getattr(live_match, "is_speaking", False)) if live_match else False,
```

Mirror the same in the orphan-live-session block below it.

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/api.py
git commit -m "daemon: expose workspace_group + auto_mode + output_destination + is_speaking on /api/sessions"
```

### Task A5: Audio worker routes per `output_destination`

**Files:**
- Modify: `core/claude_code_talker/audio.py` (worker `_run`)

- [ ] **Step 1: Resolve destination + suppress playback per rule**

Replace the existing playback gate (after `wav = engine.synthesize(...)`) with:

```python
# v0.1.0 unification — resolve per-session output destination.
dest = self._resolve_output_destination(job)
companion_owns = self._companion_owns_audio(job)
self._publish_to_audio_hub(job, wav) if dest in ("companion", "both") else None
if dest in ("desktop", "both"):
    # Suppress local play only when destination explicitly excludes desktop.
    play_audio_bytes(wav, audio_format=job.audio_format, handle=self._handle)
elif dest == "desktop":
    play_audio_bytes(wav, audio_format=job.audio_format, handle=self._handle)
# dest == "none" or unrecognized → skip both
self._publish_event(job, "done")
```

Add helper method on the worker class:

```python
def _resolve_output_destination(self, job) -> str:
    """Returns "desktop", "companion", "both", or "none"."""
    sid = getattr(job, "session_id", "") or ""
    persistent = None
    if sid:
        ps = getattr(self._state, "persistent_sessions", None)
        if ps is not None:
            persistent = ps.get(sid)
    if persistent and "output_destination" in persistent:
        return persistent["output_destination"]
    # Fall back to fleet default. companion_suppress_desktop=True maps to
    # "companion" (companion takes over); False maps to "both" (default).
    if bool(getattr(self._state, "cfg", {}).get("companion_suppress_desktop", False)):
        return "companion"
    return "both"
```

- [ ] **Step 2: Run existing audio tests**

```bash
cd core && python -m pytest tests/test_audio_companion_fanout.py -v
```

Expected: PASS (tests don't set output_destination so default "both" applies, same as before).

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/audio.py
git commit -m "daemon: audio worker routes per output_destination"
```

### Task A6: Session in-memory state gains `is_speaking` + interaction timestamps

**Files:**
- Modify: `core/claude_code_talker/sessions.py` (dataclass or Session class)

- [ ] **Step 1: Locate the Session class definition + add fields**

Grep `class Session` in `sessions.py`. In the field list, add:

```python
is_speaking: bool = False
last_user_interaction_at: float = 0.0
last_manual_mode_change_at: float = 0.0
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/sessions.py
git commit -m "daemon: add transient is_speaking + interaction timestamps to Session"
```

### Task A7: Audio worker sets/clears `is_speaking` around synthesis

**Files:**
- Modify: `core/claude_code_talker/audio.py` (worker `_run`)

- [ ] **Step 1: Wrap the synthesize+play block with flag toggles**

Just before `wav = engine.synthesize(...)`, set:

```python
self._set_speaking(job, True)
try:
    wav = engine.synthesize(job.text, job.voice, job.rate)
    # ... existing publish + play logic ...
finally:
    self._set_speaking(job, False)
```

Add helper:

```python
def _set_speaking(self, job, val: bool) -> None:
    sid = getattr(job, "session_id", "") or ""
    if not sid:
        return
    sessions = getattr(self._state, "sessions", None)
    if sessions is None:
        return
    s = sessions.get(sid)
    if s is not None:
        s.is_speaking = val
```

- [ ] **Step 2: Commit**

```bash
git add core/claude_code_talker/audio.py
git commit -m "daemon: audio worker sets is_speaking around synthesis"
```

### Task A8: Auto-mode evaluator + hook wiring

**Files:**
- Modify: `core/claude_code_talker/sessions.py` (add `evaluate_auto_mode` function)
- Modify: `core/claude_code_talker/hook_cli.py` (bump `last_user_interaction_at`, call evaluator)

- [ ] **Step 1: Add `evaluate_auto_mode` module-level function in sessions.py**

```python
import time as _time_mod

def evaluate_auto_mode(state, sid: str) -> None:
    """v0.1.0 unification — auto-switch active_mode between live/brief based on
    user interaction recency. No-op when auto_mode_enabled is false for sid."""
    if state.persistent_sessions is None:
        return
    persistent = state.persistent_sessions.get(sid) or {}
    if not persistent.get("auto_mode_enabled", False):
        return
    session = state.sessions.get(sid)
    if session is None:
        return
    # Grace window after a manual override — auto-mode pauses for 60s so the
    # user's manual pick isn't immediately overwritten.
    now = _time_mod.time()
    last_manual = getattr(session, "last_manual_mode_change_at", 0.0)
    if last_manual and (now - last_manual) < 60.0:
        return
    threshold = float(
        persistent.get(
            "auto_mode_idle_threshold_secs",
            getattr(state, "cfg", {}).get("auto_mode_idle_threshold_secs", 30.0),
        )
    )
    idle = now - float(getattr(session, "last_user_interaction_at", 0.0) or 0.0)
    target = "live" if idle < threshold else "brief"
    current = (state.sessions.config_for(sid) or {}).get("active_mode")
    if current == target:
        return
    state.sessions.update_overlay(sid, {"active_mode": target})
```

- [ ] **Step 2: Wire the evaluator into hook handlers**

In `hook_cli.py`, find the `handle_hook` (or equivalent dispatcher) that branches on event name. Before responding, add:

```python
if event_name == "UserPromptSubmit":
    s = state.sessions.get(sid)
    if s is not None:
        s.last_user_interaction_at = time.time()
from claude_code_talker.sessions import evaluate_auto_mode
evaluate_auto_mode(state, sid)
```

Also in `companion/api.py:inject`, after the buddy stream completes successfully, bump:

```python
s = state.sessions.get(active_sid)
if s is not None:
    s.last_user_interaction_at = time.time()
from claude_code_talker.sessions import evaluate_auto_mode
evaluate_auto_mode(state, active_sid)
```

- [ ] **Step 3: Commit**

```bash
git add core/claude_code_talker/sessions.py core/claude_code_talker/hook_cli.py core/claude_code_talker/companion/api.py
git commit -m "daemon: add auto-mode evaluator + wire to UserPromptSubmit + buddy inject"
```

### Task A9: Restart daemon + smoke test

- [ ] **Step 1: Restart daemon with `CCT_DAEMON_HOST=0.0.0.0`**

```powershell
Stop-Process -Id (Get-NetTCPConnection -State Listen -LocalPort 17832).OwningProcess -Force
$env:CCT_DAEMON_HOST = "0.0.0.0"
Start-Process claude-code-talker -ArgumentList serve -WindowStyle Hidden
```

- [ ] **Step 2: Verify endpoint shape**

```bash
curl -s -H "X-CCT-Pairing-Token: <token>" http://127.0.0.1:17832/api/companion/sessions | jq '.[0] | {is_speaking, auto_mode_enabled, output_destination, workspace_group, project_dir}'
```

Expected: all five fields present (most null/false on a fresh restart).

---

## Phase B — Pro Android

### Task B1: Extend SessionLite + DaemonClient parse

**Files:**
- Modify: `companion-android/app/src/main/kotlin/dev/opencircuit/codetalker/net/DaemonClient.kt`

- [ ] **Step 1: Add three fields to SessionLite**

```kotlin
val isSpeaking: Boolean = false,
val autoModeEnabled: Boolean = false,
val outputDestination: String? = null,  // "desktop"|"companion"|"both"|"none"|null
```

- [ ] **Step 2: Parse them in `listSessions()`**

```kotlin
isSpeaking = o.optBoolean("is_speaking", false),
autoModeEnabled = o.optBoolean("auto_mode_enabled", false),
outputDestination = if (o.has("output_destination") && !o.isNull("output_destination"))
    o.optString("output_destination", "").ifBlank { null } else null,
```

- [ ] **Step 3: Add helper methods**

```kotlin
fun setOutputDestination(sessionId: String, destination: String) {
    putOverlay(sessionId, mapOf("output_destination" to destination))
}
fun setAutoMode(sessionId: String, enabled: Boolean) {
    putOverlay(sessionId, mapOf("auto_mode_enabled" to enabled))
}
```

- [ ] **Step 4: Commit**

### Task B2: SessionDetail Destination + Auto-mode UI

**Files:**
- Modify: `companion-android/app/src/main/kotlin/dev/opencircuit/codetalker/ui/SessionDetailScreen.kt`

- [ ] **Step 1: Add a Destination section after Speaking mode**

```kotlin
SectionHeader("Audio destination")
DestinationPicker(current = session.outputDestination) { dest ->
    applyOverlay(mapOf("output_destination" to dest))
}
Spacer(Modifier.height(16.dp))
```

- [ ] **Step 2: Add an Auto-mode toggle below the Mode section**

```kotlin
Row(verticalAlignment = Alignment.CenterVertically) {
    Switch(checked = session.autoModeEnabled, onCheckedChange = { applyOverlay(mapOf("auto_mode_enabled" to it)) })
    Spacer(Modifier.width(8.dp))
    Column {
        Text("Auto-switch by activity", fontSize = 13.sp)
        Text("Briefs background work, goes live when you interact.", fontSize = 11.sp, color = Color(0xFF8B91A0))
    }
}
```

- [ ] **Step 3: Add `DestinationPicker` Composable**

```kotlin
@Composable
private fun DestinationPicker(current: String?, onChange: (String) -> Unit) {
    Row(modifier = Modifier.clip(RoundedCornerShape(4.dp)).background(Color(0xFF1E2230))) {
        listOf("desktop" to "Desktop", "companion" to "Glasses", "both" to "Both", "none" to "Off").forEach { (key, label) ->
            val selected = (current ?: "both") == key
            Text(
                label,
                color = if (selected) Color.White else Color(0xFF94A3B8),
                fontSize = 11.sp,
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                modifier = Modifier
                    .background(if (selected) Color(0xFF334155) else Color.Transparent)
                    .clickable { onChange(key) }
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
    }
}
```

- [ ] **Step 4: Commit**

### Task B3: Session list flash uses is_speaking + recency

**Files:**
- Modify: `companion-android/app/src/main/kotlin/dev/opencircuit/codetalker/ui/SessionListScreen.kt`

- [ ] **Step 1: Change the `isRecentlyActive` line**

```kotlin
val isSpeaking = session.isSpeaking
val isRecentlyActive = session.isLive && (nowSec - session.lastHookAt < 10.0)
val pulseStrength = when {
    isSpeaking -> 1.0f
    isRecentlyActive -> pulse * 0.7f
    else -> 0.0f
}
val borderColor = when {
    isActive -> Color(0xFF34D399)
    pulseStrength > 0f -> Color(0xFFFB923C).copy(alpha = pulseStrength)
    session.isLive -> Color(0xFF34D399).copy(alpha = 0.5f)
    else -> Color(0xFF3F3F46)
}
```

- [ ] **Step 2: Show auto-mode ribbon on the brief/live pill**

In the ModeQuickPick area, if `session.autoModeEnabled`, prepend a small `↻` chip.

- [ ] **Step 3: Commit**

### Task B4: Build + install + verify

- [ ] **Step 1: Build**

```powershell
cd companion-android
./gradlew.bat assembleDebug
```

- [ ] **Step 2: Install**

```powershell
adb -s 192.168.1.132:39315 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s 192.168.1.132:39315 shell am force-stop dev.opencircuit.codetalker
adb -s 192.168.1.132:39315 shell am start -n dev.opencircuit.codetalker/.MainActivity
```

- [ ] **Step 3: Manual verify**

Open any session detail, see the new Destination picker + Auto-mode toggle. Toggle, then verify via `curl /api/companion/sessions` that the field changed.

---

## Phase C — Webui

### Task C1: Extend `Session` + `SessionConfig` types

**Files:**
- Modify: `core/claude_code_talker/webui/src/types.ts`

- [ ] **Step 1: Add new fields**

```typescript
export interface Session {
  // ... existing fields ...
  is_speaking?: boolean;
  auto_mode_enabled?: boolean;
  output_destination?: "desktop" | "companion" | "both" | "none" | null;
  workspace_group?: string | null;
  project_dir?: string | null;
}
```

- [ ] **Step 2: Commit**

### Task C2: FilterChips component

**Files:**
- Create: `core/claude_code_talker/webui/src/components/FilterChips.tsx`

- [ ] **Step 1: Write the component**

```typescript
type Filter = "live" | "all" | "dormant" | "active";
const PILLS: { key: Filter; label: string }[] = [
  { key: "live", label: "Live" },
  { key: "all", label: "All" },
  { key: "dormant", label: "Dormant" },
  { key: "active", label: "Active" },
];

export function FilterChips({
  current,
  counts,
  onChange,
}: {
  current: Filter;
  counts: Record<Filter, number>;
  onChange: (f: Filter) => void;
}) {
  return (
    <div className="flex gap-1 px-3 py-2 border-b border-zinc-800">
      {PILLS.map((p) => (
        <button
          key={p.key}
          onClick={() => onChange(p.key)}
          className={
            "px-2 py-0.5 rounded text-xs " +
            (current === p.key
              ? "bg-cyan-700 text-white"
              : "bg-zinc-800 text-zinc-400 hover:text-zinc-200")
          }
        >
          {p.label} · {counts[p.key] ?? 0}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

### Task C3: WorkspaceGroupSection component

**Files:**
- Create: `core/claude_code_talker/webui/src/components/WorkspaceGroupSection.tsx`

- [ ] **Step 1: Write the section composable**

```typescript
import { useState } from "react";
import type { Session } from "../types";
import { SessionRow } from "./SessionRow";

export function WorkspaceGroupSection({
  label,
  sessions,
  defaultCollapsed = false,
}: {
  label: string;
  sessions: Session[];
  defaultCollapsed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const liveCount = sessions.filter((s) => s.is_live).length;
  return (
    <section>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full text-left px-3 py-2 sticky top-0 bg-[var(--color-surface-1)] border-b border-zinc-800 flex gap-2 items-center"
      >
        <span className="text-zinc-500">{collapsed ? "▸" : "▾"}</span>
        <span className="uppercase font-semibold text-xs text-[var(--color-text-1)]">{label}</span>
        <span className="text-xs text-zinc-500">
          {liveCount} live · {sessions.length} total
        </span>
      </button>
      {!collapsed && (
        <div className="px-3 py-2 space-y-1">
          {sessions.map((s) => (
            <SessionRow key={s.session_id} session={s} />
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Commit**

### Task C4: SessionRow (compact card)

**Files:**
- Create: `core/claude_code_talker/webui/src/components/SessionRow.tsx`

- [ ] **Step 1: Write the row matching Pro Android visual + control set**

```typescript
import { useState } from "react";
import { motion } from "framer-motion";
import type { Session } from "../types";
import { useSessionConfig } from "../hooks/useSessionConfig";
import { api } from "../api/client";
import { useQueryClient } from "@tanstack/react-query";

export function SessionRow({ session }: { session: Session }) {
  const { data: config } = useSessionConfig(session.session_id);
  const qc = useQueryClient();
  const muted = config?.enabled === false;
  const isSpeaking = !!session.is_speaking;
  const recent = session.is_live && session.last_modified && (Date.now() / 1000 - session.last_modified < 10);
  const borderClass = isSpeaking
    ? "border-l-orange-400"
    : recent
    ? "border-l-orange-400/60"
    : session.is_live
    ? "border-l-emerald-500"
    : "border-l-zinc-700";

  const setMute = () => api.putOverlay(session.session_id, { enabled: muted }).then(() => qc.invalidateQueries({ queryKey: ["session-config", session.session_id] }));
  const setMode = (m: string) => api.putOverlay(session.session_id, { active_mode: m }).then(() => qc.invalidateQueries({ queryKey: ["session-config", session.session_id] }));

  return (
    <motion.div
      layout
      className={"rounded border border-zinc-800 border-l-4 p-2 bg-[var(--color-surface-1)] flex items-center gap-2 " + borderClass}
      animate={isSpeaking ? { opacity: [0.6, 1, 0.6] } : { opacity: 1 }}
      transition={isSpeaking ? { duration: 1.0, repeat: Infinity } : {}}
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold truncate">{session.display_name || session.session_id.slice(0, 8)}</div>
        <div className="text-xs text-zinc-500 truncate">{session.session_id.slice(0, 12)}</div>
      </div>
      <button onClick={setMute} className={"px-2 py-0.5 rounded text-xs " + (muted ? "bg-rose-900 text-rose-200" : "bg-zinc-800 text-zinc-200")}>
        {muted ? "Unmute" : "Mute"}
      </button>
      <div className="flex rounded overflow-hidden bg-zinc-800">
        {["brief", "live"].map((m) => (
          <button key={m} onClick={() => setMode(m)} className={"px-2 py-0.5 text-xs " + (config?.active_mode === m ? "bg-slate-600 text-white" : "text-zinc-400")}>
            {session.auto_mode_enabled && config?.active_mode === m ? "↻ " : ""}
            {m}
          </button>
        ))}
      </div>
    </motion.div>
  );
}
```

- [ ] **Step 2: Commit**

### Task C5: SessionDetailPanel

**Files:**
- Create: `core/claude_code_talker/webui/src/components/SessionDetailPanel.tsx`

- [ ] **Step 1: Write the panel reusing existing pickers**

(Full code in spec — composes existing SessionControls + new DestinationPicker + AutoModeSwitch + display_name TextInput + workspace_group TextInput. ~120 lines.)

- [ ] **Step 2: Commit**

### Task C6: SessionGrid rewrite as grouped row list

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/SessionGrid.tsx`

- [ ] **Step 1: Replace flat live grid with filter chips + grouped row list**

```typescript
import { useMemo, useState } from "react";
import { useSessions } from "../hooks/useSessions";
import { FilterChips } from "./FilterChips";
import { WorkspaceGroupSection } from "./WorkspaceGroupSection";
import type { Session } from "../types";

type Filter = "live" | "all" | "dormant" | "active";

function workspaceLabel(s: Session): string {
  if (s.workspace_group) return s.workspace_group;
  if (s.project_dir) {
    const parts = s.project_dir.split("-").filter((p) => p && p !== "C" && p !== "c");
    return parts.slice(-2).join(" / ") || "Ungrouped";
  }
  if (s.project_slug) return s.project_slug;
  return "Ungrouped";
}

export function SessionGrid() {
  const { data, isLoading } = useSessions();
  const [filter, setFilter] = useState<Filter>("live");
  const sessions = data ?? [];

  const counts = {
    live: sessions.filter((s) => s.is_live).length,
    all: sessions.length,
    dormant: sessions.filter((s) => !s.is_live).length,
    active: sessions.filter((s) => s.is_companion_active).length,
  };

  const filtered = useMemo(() => {
    return sessions.filter((s) => {
      if (filter === "live") return s.is_live;
      if (filter === "dormant") return !s.is_live;
      if (filter === "active") return !!s.is_companion_active;
      return true;
    });
  }, [sessions, filter]);

  const grouped = useMemo(() => {
    const map = new Map<string, Session[]>();
    for (const s of filtered) {
      const label = workspaceLabel(s);
      if (!map.has(label)) map.set(label, []);
      map.get(label)!.push(s);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  if (isLoading) return <div className="p-6 text-zinc-500">Loading sessions…</div>;
  if (sessions.length === 0) return <div className="p-6 text-zinc-500">No sessions in catalog.</div>;

  return (
    <div className="flex flex-col h-full">
      <FilterChips current={filter} counts={counts} onChange={setFilter} />
      <div className="flex-1 overflow-y-auto">
        {grouped.length === 0 && <div className="p-6 text-zinc-500">No sessions match the "{filter}" filter.</div>}
        {grouped.map(([label, rows]) => (
          <WorkspaceGroupSection key={label} label={label} sessions={rows} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

### Task C7: Preferences global default destination + Pro badge

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/PreferencesPanel.tsx`
- Modify: `core/claude_code_talker/webui/src/features/characters/CharactersTab.tsx`

- [ ] **Step 1: Add destination default segment in PreferencesPanel**

A simple segment that posts to `/api/cfg` with `companion_suppress_desktop`.

- [ ] **Step 2: Add Pro badge in CharactersTab header**

```typescript
<div className="flex items-center gap-2">
  <h1 className="text-lg font-bold">Characters</h1>
  <span className="px-2 py-0.5 rounded text-xs bg-amber-900 text-amber-200">Pro feature</span>
</div>
<p className="text-xs text-zinc-500">Local voice cloning and animated characters are Pro features. Web creation flows are moving to the Pro Android app in a future release.</p>
```

- [ ] **Step 3: Commit**

### Task C8: Build webui + smoke test

- [ ] **Step 1: Build**

```bash
cd core/claude_code_talker/webui && npm run build
```

- [ ] **Step 2: Open in browser and verify**

Filter chips work, groups render with correct labels + counts, mute toggle round-trips, mode quick-pick round-trips, Characters tab shows Pro badge.

---

## Verification (end of plan)

- [ ] Pro Android + webui both show the same workspace groupings for the same session set.
- [ ] Muting a session from the Pro Android reflects on the webui within 5s, and vice versa.
- [ ] Setting `output_destination = companion` on a session → buddy inject test plays only through glasses; setting `desktop` → only through desktop; setting `both` → both; `none` → neither.
- [ ] Sessions with `is_speaking = true` pulse a strong orange border on both surfaces.
- [ ] Toggling Auto-mode on, then opening Claude Code and submitting a prompt, flips the session into `live`. Letting it sit idle for 30s flips it back to `brief`.
