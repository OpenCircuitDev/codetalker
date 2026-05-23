# CodeTalker — User Guide

How to actually use codetalker once it's installed and the webui is open. The README handles install; this is everything after.

---

## The first 60 seconds

Open the webui (typically `http://127.0.0.1:<auto-port>/`). You'll see four tabs along the top: **Sessions** (default), **Activity**, **Analysis**, **Preferences**.

The Sessions tab shows one row per Claude Code session you've ever run. The top bar has a master **Narration ON/OFF** toggle — flip this off and codetalker stays quiet without losing any session state.

Each session row has:
- A **health chip** (●/◐/⊗/○ = running / working / blocked / dormant)
- The session name
- A **mode dropdown** (brief / live / direct / critical_only — see below)
- A **mute** toggle
- Sink chips showing where audio goes (Desktop / Phone / Glasses)

Right panel shows a live narration log scrolling as the daemon speaks.

---

## Choosing your mode by work style

Each session can run in a different mode at any time. Switch via the dropdown on the row.

| If you want… | Pick |
|---|---|
| To step away for 5 min and come back to a one-sentence summary | **brief** |
| A running commentary while you focus on something else | **live** |
| The deepest possible detail (raw tool outputs) | **direct** |
| Silence unless something breaks, blocks, or needs you | **critical_only** |

**Defaults to brief.** Switch to `critical_only` for sessions you're listening to on a commute or while doing other work; switch to `live` when you want the conversation feel; switch to `direct` only when you're debugging the narrator itself.

---

## What you'll hear (audible vocabulary)

The narrator emits a small set of distinct phrases that always mean the same thing. Once you learn these, you can listen passively and react only to the ones that matter:

| Cue | Meaning |
|---|---|
| **"Heads up."** | An `[ALERT]` — something broke, is blocking, or needs your input right now. Drop what you're doing. |
| **"Checkpoint."** | An architectural decision was made (schema, API shape, dependency add, migration approach). Worth being aware of. |
| **"Still here."** | Heartbeat — daemon's alive but nothing's worth saying yet. (No action needed.) |
| **"Still here. Quiet two minutes."** | Second heartbeat — alive but quieter than expected. |
| **"Still on it — N minutes."** | Sustained silence — the AI's working, but no events have fired in N minutes. May genuinely be stuck. |

You'll also hear normal-sounding narrations with **assumption clauses** ("assuming JSON not protobuf"), **diff clauses** ("was per-request; now cached"), **WHY clauses** ("instead of a JOIN"), and **backtrack clauses** ("abandoned the JOIN — planner won't use the index").

Numbers, IP addresses, ISO timestamps, currency amounts, and code-fence content are normalized for natural pronunciation — no "one nine two dot one six eight dot one dot one" or "asterisk asterisk asterisk." Markdown bullet lists become spoken sentences with natural pauses between items.

For the full cue legend with descriptions, open **Preferences → Spoken Cues**.

---

## Catching up after you've been away

Three tools, increasing in scope:

- **Rewind 30s** pill (top bar) — replays the last half-minute of audio for the active session. Use when you missed the last thing said.
- **Skip** pill (top bar) — drops the current narration mid-sentence. Use when what's playing is already stale to you and the next one matters more.
- **Decisions Only** filter in Activity tab — hides every non-`[CHECKPOINT]` event, leaving only the architectural decisions visible. Useful when reviewing async work.

For the most-complete recap, the daemon also exposes `POST /api/audio/replay-decisions` — fires every checkpoint from the last 30 minutes through the speaker as a highlight reel. (Webui button for this is on the backlog.)

---

## Multi-session listening

Most users end up with 3-5 sessions active at once.

- **Workspace groups** let you organize sessions by project. Set via the group dropdown on each row, or via `PATCH /api/sessions/{sid}` with `workspace_group: "MyProject"`. Groups are case-insensitive and merge automatically.
- **Pin** the session you most care about within a group — pinned rows stay at the top regardless of activity.
- **Blocked-first sort** — within each group, codetalker shows the **blocked** sessions first, then **working**, **running**, **dormant**. The amber banner at the very top says "N sessions need attention" with clickable chips that scroll to each.
- **Mode per session** — you can keep the noisy session in `critical_only` while the one you care about runs in `live`.
- **(Pro)** Multi-session fan-in to a single phone speaker, with the active session announced explicitly when narrations come from a different one than the previous.

---

## Tuning the narrator

- **Per-session voice** — open the session row, pick from installed Piper voices.
- **Cadence** — live mode defaults to 8-12s ticks. Tighten or loosen in Preferences → Audio defaults.
- **Mute** — silence the session without losing state. (Unmute resumes immediately.)
- **Auto-mode** — opt-in: codetalker swaps live↔brief based on user-interaction recency. Off by default.
- **Markup config** — `GET /api/markup/config` to inspect current pronunciation rules (number forms, code fences, bullets); `PUT` to override per-form behavior.

---

## Common gotchas

| Symptom | Likely cause | Fix |
|---|---|---|
| "Not hearing any audio" | Master toggle off, or session's `audio_outputs` doesn't include `desktop` | Top-bar toggle, or `PATCH /api/sessions/{sid}` with `audio_outputs: ["desktop"]` |
| "Narrator won't shut up" | Session in `live` when you wanted `brief` | Change mode dropdown |
| "Hearing old stuff as if new" | Stale-prose bleed (fixed in commit `ff765bd` — restart daemon if older) | Restart daemon to pick up the 180s freshness gate |
| "Multiple sessions sound the same" | No per-session voices configured | Preferences → Voices → assign a distinct voice to each session |
| "Phone goes silent every few minutes" | Phone subscription dropped (NAT timeout) | Toggle the phone's "active session" off and back on, OR restart the Android app |
| "TTS pronounces 'asterisk'" | Old daemon version pre-bullet-fix | Restart — the markup pipeline strips bullets |

---

## Pro vs Basic

| Feature | Basic | Pro |
|---|---|---|
| Desktop browser narration (webui) | ✓ | ✓ |
| Four narration modes (brief/live/direct/critical_only) | ✓ | ✓ |
| All audible cues + WHY/diff/backtrack/assumption clauses | ✓ | ✓ |
| Workspace grouping, session pinning, health badge | ✓ | ✓ |
| Rewind / Skip / Replay decisions | ✓ | ✓ |
| Android companion app (phone speaker) | – | ✓ |
| Local voice cloning (XTTS, your 10s sample) | – | ✓ |
| Buddy mode (talk to the agent through the phone) | – | ✓ |
| Direct STT (voice-to-Claude dictation) | – | ✓ |
| Multi-session fan-in to one phone | – | ✓ |
| Character library (3D avatars, persona bundles) | – | ✓ |
| XREAL AR glasses integration | – | ✓ (optional) |

The Basic tier is fully featured for desktop listening. Pro adds the mobile/voice/visual layer.

---

## Where to go next

- `docs/PERSONA_INSIGHTS.md` — how 50 vibe-developer personas score the product across 10 iterations
- `docs/API_QUICKREF.md` — HTTP endpoints if you're building a custom client
- `docs/VOICE_COMMAND_DESIGN.md` — design spec for the upcoming "Hey CodeTalker" feature
- `docs/UX_AUDIT.md` — accessibility + visual-design notes for the webui chips and badges
- `CHANGELOG_2026_05_21.md` — recap of the one-day burst that landed most of the features above
