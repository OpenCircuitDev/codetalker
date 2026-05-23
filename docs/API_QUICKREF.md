# CodeTalker daemon — HTTP API quickref

The daemon runs a Starlette ASGI app on a local port (auto-assigned; default `~/.claude/scripts/codetalker/.daemon-port` records it). All routes are unauthenticated — local trust. Examples use `$PORT` as a stand-in.

```bash
PORT=$(cat ~/.claude/scripts/codetalker/.daemon-port)
```

## Health & status

### `GET /api/health`
Quick liveness check. Used by webui to gate the green dot in the top bar.
```bash
curl -s http://127.0.0.1:$PORT/api/health
# → {"ok": true, "narration_enabled": true, "narration_warning": null}
```

### `GET /api/status`
Fuller status — includes daemon uptime, active sessions, voice engine status.

### `GET /api/master-enabled` / `PUT /api/master-enabled`
The global narration on/off toggle (top-bar switch in webui).
```bash
curl -X PUT http://127.0.0.1:$PORT/api/master-enabled \
  -H "Content-Type: application/json" -d '{"enabled": false}'
```

---

## Sessions

### `GET /api/sessions`
List all known sessions (live + dormant in catalog). Returns array of `SessionView` dicts: `session_id`, `display_name`, `cwd`, `project_slug`, `workspace_group`, `active_mode`, `audio_outputs`, `is_live`, `is_speaking`, `last_modified`, `last_hook_at`, `pinned`, `attached_character`, etc.

### `GET /api/sessions/{session_id}`
Single session view, same shape as the list entry.

### `PATCH /api/sessions/{session_id}`
Mutate persistent overlay. Accepts any subset of:

| Field | Type | Notes |
|---|---|---|
| `enabled` | bool | mute / unmute (false = silent) |
| `active_mode` | `"brief"\|"direct"\|"live"\|"critical_only"` | per-session narration mode |
| `voice` | dict | `{model, rate}` |
| `live` | dict | `{cadence_seconds, ...}` |
| `markup` | dict | per-session markup config |
| `attached_character` | str/null | character id |
| `workspace_group` | str/null | user grouping label |
| `audio_outputs` | list[str] | subset of `["desktop","phone","glasses"]` |
| `display_name` | str/null | user-friendly rename |
| `pinned` | bool | pin-to-top within group |
| `auto_mode_enabled` | bool | opt-in auto live↔brief swap |

```bash
curl -X PATCH http://127.0.0.1:$PORT/api/sessions/$SID \
  -H "Content-Type: application/json" \
  -d '{"active_mode": "critical_only", "workspace_group": "OCR"}'
```

### `PUT /api/sessions/{session_id}/overlay`
Replace the entire overlay (rather than merge). Use sparingly — `PATCH` is usually right.

### `POST /api/sessions/bulk`
Bulk-mute / bulk-mode-set across many sessions in one call.

### `POST /api/sessions/{session_id}/attach-character` / `DELETE .../character`
Attach or detach a Character (Pro voice + persona bundle).

### `POST /api/sessions/{session_id}/save-as-profile`
Snapshot the current overlay as a reusable profile.

### `POST /api/sessions/{session_id}/chat`
Send a synthetic user message to the session (Pro feature; equivalent of `companion/inject` for desktop testing).

---

## Persistent overlay (lower-level access)

### `GET /api/persistent-sessions/{session_id}`
Read the raw persistent overlay (as stored in the SQLite-backed `SessionStore`). The PATCH endpoint above is the canonical write path; this is for inspection / debugging.

### `PUT /api/persistent-sessions/{session_id}`
Replace the full overlay payload. Bypasses the PATCH merge logic.

### `DELETE /api/persistent-sessions/{session_id}`
Drop the overlay (revert to defaults).

---

## Audio control

### `POST /api/audio/skip`
Cancel the currently-playing TTS and clear queued narrations for this session (or globally).
```bash
curl -X POST http://127.0.0.1:$PORT/api/audio/skip \
  -H "Content-Type: application/json" -d '{}'
# → {"skipped": true}
```

### `POST /api/audio/rewind`
Replay the last N seconds of audio for the active session (default 30s).
```bash
curl -X POST http://127.0.0.1:$PORT/api/audio/rewind \
  -H "Content-Type: application/json" -d '{"seconds": 30}'
```

### `POST /api/audio/replay-decisions`
Replay only `[CHECKPOINT]` narrations from the last N minutes — a highlight reel of architectural decisions. `priority=routine` so it won't interrupt live narrations.
```bash
curl -X POST http://127.0.0.1:$PORT/api/audio/replay-decisions \
  -H "Content-Type: application/json" \
  -d '{"window_seconds": 1800, "session_id": null}'
# → {"replayed": 2, "window_seconds": 1800, "session_id": null}
```

---

## Audio job audit trail

### `GET /api/audio-jobs/recent?n=50`
Ring-buffered list of recent AudioJob records (each with state_history showing created → synthesizing → playing → played transitions).

### `GET /api/audio-jobs/{job_id}`
Single job by id.

---

## Narration log

### `GET /api/narration-log?n=50`
Tail of the append-only narration audit log. Each entry: `timestamp, session_id, text, voice, mode, confidence, checkpoint, alert`.

### `GET /api/narration-stream` (SSE)
Server-sent-events stream of narration events as they fire. Includes `alert` / `checkpoint` / `confidence` flags so the webui can render the right badges in real time.
```bash
curl -N http://127.0.0.1:$PORT/api/narration-stream
```

### `GET /api/events` (SSE)
Lower-level event firehose (hooks, focus changes, mode swaps).

---

## Analysis reports (market analysis tab)

### `GET /api/analysis-reports`
List the `MARKET_ANALYSIS_*.md` files at repo root. Each entry: `{filename, label, size, modified}`. Sorted newest first.

### `GET /api/analysis-reports/{filename}`
Raw markdown content. Filename is validated against `MARKET_ANALYSIS_*.md` to block path traversal.

---

## Companion (Pro app endpoints)

### `POST /api/companion/pair`
QR-token pairing handshake for the Android app.

### `GET /api/companion/sessions`
List sessions visible to the phone (mirrors `/api/sessions` shape).

### `POST /api/companion/active-session`
Tell the daemon which session(s) the phone is actively listening to. The daemon uses this to gate phone-bound audio routing.
```bash
curl -X POST http://127.0.0.1:$PORT/api/companion/active-session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc...", "active": true}'
```

### `POST /api/companion/inject`
Inject a synthetic user message into a session (Buddy mode reply).

### `POST /api/companion/direct-stt`
Send a dictated user message directly to Claude (Direct STT).

### `POST /api/companion/start-buddy`
Begin a buddy-mode reply turn for a specific session.

### `GET /api/companion/audio-stream/{session_id}` (SSE)
Streams TTS audio frames to the phone's TTSPlayer.

---

## Licensing

### `GET /api/license/status`
Current Pro license state: `{has_license, pro_active, expires_at, ...}`.

### `POST /api/license/activate`
Activate a license key issued by the website.
```bash
curl -X POST http://127.0.0.1:$PORT/api/license/activate \
  -H "Content-Type: application/json" \
  -d '{"key": "CT-9828-E988-7292-F345-7DDB"}'
```

---

## Voices & characters

### `GET /api/voices` / `GET /api/voices/list`
Installed Piper / Coqui voice list.

### `POST /api/voices/clone-from-file` (Pro)
Submit a 10-second voice sample for XTTS cloning.

### `GET /api/characters` / `POST /api/characters`
Character library CRUD (Pro feature: 3D avatar + voice bundle).

### `POST /api/sessions/{session_id}/attach-character`
Attach a character to a session (governs voice + persona).

### `POST /api/sessions/{session_id}/generate-character` (Pro)
Generate a fresh character (mesh + voice) for this session via the configured provider.

---

## Markup pipeline config

### `GET /api/markup/config` / `PUT /api/markup/config`
Per-form treatment overrides (code-fence handling, IP/timestamp/currency pronunciation, status-symbol rules).

---

## Profiles

### `GET /api/profiles` / `GET /api/profiles/{name}` / `PUT /api/profiles/{name}` / `DELETE /api/profiles/{name}`
Reusable overlay snapshots. Apply via `POST /api/sessions/{sid}/attach-profile`.

---

## Triggers (per-tag narration rules)

### `GET /api/triggers/config` / `PUT /api/triggers/config`
Toggle trigger mode + cadence params.

### `GET /api/triggers/tags` / `POST /api/triggers/tags` / `PUT /api/triggers/tags/{id}` / `DELETE /api/triggers/tags/{id}`
Tag CRUD: each tag maps a pattern to a narration template.

---

## Catalog

### `GET /api/catalog`
List session IDs the daemon has ever seen (vs `GET /api/sessions` which is the active+persistent intersection).

### `POST /api/catalog/refresh`
Force a fresh scan of `~/.claude/projects/`.

---

## Secrets

### `GET /api/secrets` / `PUT /api/secrets`
Per-provider API keys (OpenRouter, OpenAI, Anthropic). Stored in `~/.claude/scripts/codetalker/secrets.json`; values are never returned in GET — only `{has_<provider>: true/false}` flags.

---

## Hooks plumbing

### `GET /api/hooks-status`
Did `~/.claude/settings.json` install the codetalker hook entries? Returns `{installed: bool, missing: [...]}`.

### `POST /api/install-hooks`
Write the hook entries into `settings.json`.

### `POST /api/hooks/dispatch`
Internal endpoint the `claude-code-talker-hook` CLI calls. Not for external clients.

---

## Skipped here (internal / debug only)

- `/api/virtual-eval/*` — automated narration eval; called by `scripts/virtual_eval.py` not by clients
- `/api/tts-cache` — internal cache stats
- `/api/usage` — internal token-spend accounting
- `/api/config/reload` — admin reload
- `/api/llm-models/openrouter/refresh` — admin
- `/api/mesh-providers`, `/api/mesh-jobs` — internal 3D mesh-generation queue

---

## Used by

- **Webui**: SessionGrid + ActivityTab + Preferences + AnalysisTab — most of `/api/sessions`, `/api/narration-*`, `/api/audio/*`, `/api/analysis-reports`, `/api/characters`, `/api/voices`
- **Android Pro app**: `/api/companion/*` + `/api/sessions` for the Sessions screen + `/api/audio/skip` for the global Skip pill
- **`claude-code-talker-hook` CLI**: only `/api/hooks/dispatch`
- **`scripts/market_analysis.py`**: indirect — reads `~/.claude/scripts/codetalker/narration-log.jsonl` directly, doesn't hit the daemon
