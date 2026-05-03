# Phase 7 Web UI Smoke Test Checklist

Manual verification for the multi-session web control panel. Run after `pip install -e core/` and once the daemon is healthy.

---

## §0 Pre-flight

- [ ] `pip install -e core/` succeeds
- [ ] `claude-code-talker` (no args) prints engines + providers list
- [ ] `claude-code-talker serve &` binds to `127.0.0.1:17832`
- [ ] `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:17832/api/health` returns `200`

---

## §1 Web UI loads

- [ ] Open `http://127.0.0.1:17832/ui/` in any browser
- [ ] Page renders dark theme: sidebar (left, "codetalker" title) + detail pane (right)
- [ ] Sidebar shows "Active sessions (0)" with empty-state message + "install hooks" link
- [ ] Sidebar shows "Profiles" section (empty)
- [ ] Detail pane shows "Select a session from the sidebar." muted text
- [ ] Mute toggle (top-right of sidebar) shows 🔊 (or 🔇 if previously muted)

---

## §2 Mute toggle

- [ ] Click the mute button — icon flips between 🔊 and 🔇
- [ ] `curl -s http://127.0.0.1:17832/api/status | jq .enabled` matches the icon state
- [ ] Click again — flips back

---

## §3 Inject a fake session via hook CLI

- [ ] Run: `echo '{"hook_event_name":"Notification","session_id":"smoke-1","message":"hello"}' | claude-code-talker-hook`
- [ ] Within 2s, sidebar refreshes to show "smoke-1" under Active sessions
- [ ] Click "smoke-1" → detail pane shows session header (id, cwd, last hook time)
- [ ] Tab strip is visible: Quick · Audio · Behavior · Advanced

---

## §4 Tabs end-to-end

- [ ] **Quick tab**: Mode dropdown (direct/brief/live), Voice dropdown (populated from engines), "Play sample" button
- [ ] Change Mode to "live" → within 2s the dropdown reflects the change persistently
- [ ] **Audio tab**: Engine, Voice, Rate fields. Change Rate to 1.3 → persists
- [ ] **Behavior tab**: Mode field always; Cadence + Significance threshold + LLM Provider appear ONLY when Mode is "live"
- [ ] **Advanced tab**: Queue max depth, Staleness, Code blocks, File paths, "Clear all overrides" button

---

## §5 Profile workflow

- [ ] Tune some Quick + Audio fields on smoke-1 (e.g., voice=jenny, rate=1.2, mode=brief)
- [ ] Click "Save as profile" → dialog opens
- [ ] Type "smoke-test" → click Save → toast confirms
- [ ] "smoke-test" appears in sidebar Profiles list
- [ ] Inject a second session: `echo '{"hook_event_name":"Notification","session_id":"smoke-2","message":"hi"}' | claude-code-talker-hook`
- [ ] Select smoke-2 → detail pane shows fresh defaults (no overlay yet)
- [ ] In the "Attach profile…" dropdown, pick "smoke-test" → toast confirms attach
- [ ] smoke-2's Quick tab now shows the smoke-test settings (voice=jenny, rate=1.2, mode=brief)
- [ ] The "▼ smoke-test" pill appears in the detail header
- [ ] Click the pill → confirms detach → settings revert to defaults

---

## §6 Profile delete cascades

- [ ] Re-attach smoke-test to both smoke-1 and smoke-2
- [ ] In sidebar Profiles list, click ✕ next to smoke-test → confirm
- [ ] Toast: "Deleted 'smoke-test' (detached from 2 sessions)"
- [ ] Both sessions show no attached profile

---

## §7 Failure modes

- [ ] Stop daemon (`claude-code-talker stop`)
- [ ] Within 10s the UI shows "Daemon offline" banner at top
- [ ] Click "retry" — banner stays (daemon's gone). Restart daemon (`claude-code-talker serve &`)
- [ ] Click "retry" — banner disappears, sessions reappear
- [ ] PUT a setting with daemon offline → toast error, form keeps the edit

---

## §8 Reattach on restart (optional but high-value)

- [ ] On any session, attach a profile (e.g., smoke-test if recreated)
- [ ] Note the cwd shown in the detail header
- [ ] Stop daemon → sessions clear
- [ ] Restart daemon
- [ ] Send another hook for the SAME session: `echo '{"hook_event_name":"Notification","session_id":"smoke-1","cwd":"<that-cwd>","message":"x"}' | claude-code-talker-hook`
- [ ] Within 2s, smoke-1 reappears in sidebar with the attached profile (auto-reattach by cwd)

---

## §9 Done

If all checkboxes pass, Phase 7 web UI is verified end-to-end. Tag:

```bash
git tag -a v0.7.0-phase7 -m "Phase 7 complete: web UI + multi-session control panel"
```

If anything fails, capture the symptom + the line that failed and report. The frontend source is small (~600 LOC across 3 files in `static/`); the daemon side is well-tested in pytest.


---

## §11 Phase 8 — Catalog + Persistent Settings

- [ ] Open `http://127.0.0.1:17832/ui/`
- [ ] Sidebar shows MORE than just live sessions — historical sessions from `~/.claude/projects/` also visible (count should match `find ~/.claude/projects -name "*.jsonl" | wc -l`, capped at 500)
- [ ] Live sessions have a green `●` prefix; inactive sessions don't
- [ ] Filter chips work: "All" shows everything; "Live" shows only `●` sessions; "Enabled" hides sessions you've muted
- [ ] Click an inactive session (no `●`) → detail pane shows the resolved config
- [ ] Change Mode to "live" on the inactive session
- [ ] Refresh the browser → the Mode change persists (loaded from `/api/persistent-sessions/<sid>`)
- [ ] Click "🔊 Disable" in the detail header → session gets `🔇` prefix in sidebar; "Disable" button flips to "🔇 Enable"
- [ ] Refresh the browser → disabled state persists
- [ ] Stop daemon, restart it (`claude-code-talker stop && claude-code-talker serve &`), open UI again
- [ ] Disabled session is STILL disabled (loaded from disk on first hook touch)
- [ ] Trigger a hook from the disabled session → daemon log shows "skipped: per-session disabled"; no audio plays
- [ ] Click "🔇 Enable" → next hook produces audio normally

---

## §12 Phase 13 — Virtual User Evaluation

- [ ] Open `http://127.0.0.1:17832/ui/`
- [ ] Click ⚙ Settings → Eval tab
- [ ] Click "Run virtual user eval"
- [ ] Within ~30s, report shows: 5 personas / N narrations / per-persona scores / systemic jargon (if any) / proposal
- [ ] If proposal has ≤3 fields → banner says "Auto-tuning applied"
- [ ] If proposal has >3 fields → banner says "approval needed"; check Tuning history list
- [ ] Tuning history list shows the entry with "Revert" button (if applied)
- [ ] Click "Revert" → confirm → entry's field reverts in `~/.claude/scripts/codetalker/cfg-overlay.yaml`
- [ ] Restart daemon → reload UI → reverted state holds
- [ ] Run eval again → verify history grows (now has 2+ entries)
