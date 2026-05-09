# CCT Phase 25a — Character data model + session attachment

**Status**: approved 2026-05-09, awaiting spec review.
**Authors**: Brand (user) + Claude (this session).
**Scope**: foundation layer of CCT Phase 25 (Characters). Phase 25b (3D model APIs) and Phase 25c (browser voice cloning UX) build on this and get their own design + plan cycles later.
**Reference**: parent roadmap entry in [2026-05-08-cct-v1-design.md](./2026-05-08-cct-v1-design.md).

## Context — why this design exists

The CCT v1 spec roadmap calls out **Phase 25 — Characters** as a future phase: a `Character` is a named bundle of voice + 3D model + persona that attaches to a Claude Code session so its narrations come out in that character's identity. The whole Phase 25 splits cleanly into three independent subsystems:

- **25a — Character data model + session attachment** *(this spec)* — the foundation. Defines what a Character is, how it's stored, how it attaches to sessions, how it interacts with the existing Profile system. Nothing user-visible ships from 25a alone; it's the contract everything else builds on.
- **25b — 3D model API adapter** — Hyper3D / Meshy / Tripo3D integrations that populate `Character.mesh_path`. Future spec.
- **25c — Browser-based voice cloning UX** — `MediaRecorder` + video extraction + `voice_ref` writeback. Future spec. Most user-facing of the three.

Doing 25a first is deliberate: 25b and 25c both depend on the Character record + storage existing. Without 25a, both have to invent ad-hoc records that would need to be migrated.

## Decisions locked in

- **Field shape**: rich record — id, display_name, voice_ref, persona, mesh fields (nullable), timestamps, prompt history.
- **Storage**: per-file YAML at `~/.claude/scripts/codetalker/characters/<id>.yaml`. Mirrors the profile pattern (`ProfileStore` at `core/claude_code_talker/profiles.py`).
- **Profile interaction**: characters and profiles coexist on a session. **Field-level precedence** — character wins for identity fields (voice, persona); profile wins for behavior fields (mode, cadence, rate, teacher_level).
- **MCP tools**: out of scope for 25a. REST endpoints only. 25c adds MCP tools when characters become user-facing.
- **Animation pipeline**: out of scope for the entire Phase 25; tracked separately as a future phase.

## Architecture

```
core/claude_code_talker/
├── characters.py                          # NEW — Character dataclass + CharacterStore
├── api.py                                 # MODIFY — add /api/characters CRUD + attach routes
├── server.py                              # MODIFY — wire CharacterStore into ServerState
├── config_resolver.py (or sessions.py)    # MODIFY — character-aware merge in config_for(sid)
└── persistent_sessions.py                 # MODIFY — add attached_character field

core/tests/
├── test_characters.py                     # NEW — Character + CharacterStore unit tests
├── test_api_characters.py                 # NEW — REST endpoint coverage
└── test_sessions_character_attach.py      # NEW — attach lifecycle + precedence

~/.claude/scripts/codetalker/characters/   # NEW — runtime storage
└── <id>.yaml                              # one file per character
```

No daemon redesign. CharacterStore mirrors ProfileStore architecturally; the cfg merge gains one new layer; REST surface gains 7 new endpoints.

## Section 1 — Character data model

New module `core/claude_code_talker/characters.py`. Python dataclass:

```python
from dataclasses import dataclass, field, asdict
from typing import Optional


VALID_PERSONAS = {"methodical", "warm", "technical", "plain", "sarcastic", "energetic"}
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class Character:
    id: str                              # kebab-case, immutable
    display_name: str                    # mutable
    voice_ref: str                       # voice name from voice library; required
    persona: str = "methodical"          # narration style; default matches today's cfg default
    mesh_path: Optional[str] = None
    mesh_provider: Optional[str] = None  # "hyper3d" | "meshy" | "tripo3d" | other
    mesh_prompt: Optional[str] = None
    mesh_prompt_history: list[str] = field(default_factory=list)
    created_at: float = 0.0              # epoch seconds; set on first save
    updated_at: float = 0.0              # epoch seconds; updated on every save

    def validate(self) -> None:
        """Raise ValueError on invalid state. Called by CharacterStore.save()."""
        if not _ID_RE.match(self.id):
            raise ValueError(f"id must be kebab-case lowercase: {self.id!r}")
        if not self.display_name.strip():
            raise ValueError("display_name required")
        if not self.voice_ref.strip():
            raise ValueError("voice_ref required")
        if self.persona not in VALID_PERSONAS:
            raise ValueError(f"persona must be one of {VALID_PERSONAS}; got {self.persona!r}")

    @classmethod
    def from_dict(cls, d: dict) -> "Character": ...
    def to_dict(self) -> dict: ...
```

**Validation strategy**: strict on save, lenient on load. CharacterStore.save() calls `validate()` and raises ValueError on bad input — caller handles. Loads tolerate missing optional fields (default-fill via the dataclass defaults). Unknown fields on load are dropped silently with a debug log.

**Voice ref resolution**: `voice_ref` references a voice by name. `Character.validate()` does NOT verify the voice exists (the voice library is loaded separately and the character may be saved before its voice is cloned via Phase 25c). The REST endpoint `POST /api/sessions/<sid>/attach-character` DOES verify and returns a 400 if the referenced voice is missing.

## Section 2 — CharacterStore (persistence)

In the same `characters.py` module, mirror `ProfileStore`:

```python
DEFAULT_CHARACTERS_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "characters"


class CharacterStore:
    def __init__(self, characters_dir: Optional[Path] = None):
        self._dir = characters_dir if characters_dir is not None else DEFAULT_CHARACTERS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Character]:
        """Return all characters sorted by display_name (case-insensitive)."""
        ...

    def get(self, char_id: str) -> Optional[Character]:
        """Return character by id, or None if missing."""
        ...

    def save(self, character: Character) -> Path:
        """Atomic write to <id>.yaml. Sets created_at on first save, updates updated_at always.
        Calls character.validate() first; raises ValueError on invalid input."""
        ...

    def delete(self, char_id: str) -> bool:
        """Remove the character file. Returns True if it existed, False if not."""
        ...
```

**Atomic-write pattern**: same as `triggers/skill.py::install_skill` — write to `<id>.yaml.tmp`, then `os.replace` to final name. No partial writes visible to readers.

**Concurrency**: last-writer-wins. The store is a thin disk wrapper; in-memory cache is rebuilt on each call (cheap — characters won't number more than ~50 per user). Future phase can add etag-based optimistic locking if needed.

## Section 3 — Session attachment + cfg merge precedence

### Persistent session record

`core/claude_code_talker/persistent_sessions.py` — extend the persistent session schema with one new field:

```python
{
  "session_id": "...",
  "enabled": True,
  "attached_profile": "alpha",        # existing
  "attached_character": "fluffy-narrator",  # NEW
  "display_name": "...",
  "live_overlay": {...},
  ...
}
```

### Cfg merge order (in `config_for(session_id)`)

Today the merge is roughly:

```
final_cfg = global_cfg + profile_cfg + session_overlay
```

After 25a:

```
final_cfg = global_cfg + profile_cfg + character_cfg(restricted) + session_overlay
```

Where `character_cfg(restricted)` is a dict containing **only the character's identity fields**, mapped into cfg shape:

```python
{
  "voice": {"model": <character.voice_ref>},
  "triggers": {"persona": <character.persona>},
}
```

The `(restricted)` part is critical: a character does NOT supply `mode`, `cadence`, `rate`, `teacher_level`, etc. Those still come from profile / session overlay / global. This is the field-level precedence locked in during the brainstorm.

The merge order ensures session overlay wins over character (user's explicit per-session intent beats character defaults), and character wins over profile for the identity fields it provides. Profile still wins for behavior fields because character doesn't supply them.

### Edge cases

- **Character attached, voice missing in library**: `config_for()` still returns the character's voice_ref. The `tts_speak` engine call fails clearly when the voice isn't found. Mitigation: `attach-character` endpoint validates voice presence at attach time.
- **Character deleted while attached to a session**: `attached_character` becomes a dangling reference. `config_for()` falls back to profile/global cfg as if no character was attached. The session catalog flags it (`attached_character` is set but `state.characters.get(...)` returns None).
- **Both profile and character attached, both supply the same field**: shouldn't happen because of the field-level restriction. If profile somehow has a `voice` (it doesn't today, but hypothetically), character wins per the brainstorm.

## Section 4 — REST API

Seven new routes added to `core/claude_code_talker/api.py:build_routes()`:

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| GET | `/api/characters` | — | `[Character]` | List all, sorted by display_name |
| GET | `/api/characters/<id>` | — | `Character` or 404 | |
| POST | `/api/characters` | `Character` (no timestamps) | `Character` (with timestamps) or 400 | Sets created_at/updated_at; 409 if id exists |
| PUT | `/api/characters/<id>` | `Character` (no timestamps) | `Character` (with updated timestamps) or 400/404 | Full replace; preserves created_at, updates updated_at |
| DELETE | `/api/characters/<id>` | — | `{"deleted": true}` or 404 | Detaches from any sessions that had this character (best-effort) |
| POST | `/api/sessions/<sid>/attach-character` | `{"character_id": "..."}` | session record or 400 | 400 if character missing or voice_ref unresolved |
| DELETE | `/api/sessions/<sid>/character` | — | session record | Idempotent — no error if not attached |

The `/api/sessions` and `/api/sessions/<id>` responses gain an `attached_character` field alongside the existing `attached_profile`. Existing fields unchanged.

**ID handling**: `<id>` and `<sid>` are URL-encoded; `_PROJECT_RE`-style validation (`^[a-z0-9-]{1,128}$`) before any file I/O. Defends against directory traversal.

**Validation errors**: 400 with `{"error": "<message>"}` body matching api.py's existing `_bad_request()` pattern.

## Section 5 — Tests

Three new test files; touches a couple of existing ones.

### `core/tests/test_characters.py` (new)

- `test_character_validate_accepts_valid_record`
- `test_character_validate_rejects_bad_id` (uppercase, spaces, leading dash, etc.)
- `test_character_validate_rejects_empty_voice_ref`
- `test_character_validate_rejects_unknown_persona`
- `test_character_from_dict_tolerates_missing_optional_fields`
- `test_character_to_dict_round_trips`
- `test_character_store_save_creates_file_at_expected_path`
- `test_character_store_save_sets_created_at_on_first_save`
- `test_character_store_save_updates_updated_at_on_every_save`
- `test_character_store_save_atomic_write_no_partial_visible` (write 1KB, kill mid-write, file is either old or new)
- `test_character_store_get_returns_none_for_missing`
- `test_character_store_list_sorted_by_display_name_case_insensitive`
- `test_character_store_delete_returns_false_for_missing`

### `core/tests/test_api_characters.py` (new)

- Each route × happy path + error cases (400, 404, 409 where applicable)
- `attach-character` validates voice_ref presence in voice library
- DELETE character cascades to detach from sessions

### `core/tests/test_sessions_character_attach.py` (new)

- Attach character → `/api/sessions/<sid>` shows `attached_character`
- `config_for(sid)` returns merged cfg with character.voice_ref as voice.model
- Profile + character coexist: profile.mode wins, character.voice wins
- Session overlay > character (user's per-session voice override beats character)
- Detach character → field becomes null
- Dangling character (deleted while attached) → cfg merge falls back to profile/global, no exception

### Existing tests touched

- `core/tests/test_persistent_sessions.py` — extend to cover the new `attached_character` field round-trip
- `core/tests/test_config_resolver.py` (or wherever `config_for` is tested today) — extend with character precedence cases

### Acceptance

- All 856 existing backend tests stay green
- All 9 webui tests stay green
- ~25 new tests added across the three new files

## Section 6 — Out of scope (deferred)

Tracked here so future Phase 25 specs can reference what 25a explicitly did NOT do:

- **Browser-based voice cloning UX** — Phase 25c. The `voice_ref` field exists but UX for creating cloned voices isn't here.
- **3D model generation API** — Phase 25b. The `mesh_*` fields exist but the providers, async tracking, and storage flow aren't here.
- **Dashboard "Characters" tab** — lands with 25c when characters become daily-use. The React UI doesn't see characters at all in 25a.
- **Character-aware MCP tools** — none. Claude can use the REST endpoints via Bash if needed; dedicated MCP tools (e.g., `tts_attach_character`) come with 25c.
- **Animation pipeline integration** — Phase 26 territory; integrates with Blender + Unreal pipelines elsewhere in the user's project.
- **Per-character cost / usage tracking** — relevant for 25b (3D APIs cost money); 25a's identity-only fields don't have spend implications.
- **Character versioning / undo** — last-writer-wins; future phase if multi-user / collaborative editing matters.

## Critical files

Modify:
- `core/claude_code_talker/api.py` — add 7 routes in `build_routes()`; extend `/api/sessions` response to include `attached_character`.
- `core/claude_code_talker/server.py` — instantiate `CharacterStore`, wire onto `ServerState.characters`.
- `core/claude_code_talker/persistent_sessions.py` — schema extension for `attached_character`.
- `core/claude_code_talker/config_resolver.py` (or wherever `config_for(session_id)` lives — verify during implementation) — character-aware merge.

Create:
- `core/claude_code_talker/characters.py` — Character + CharacterStore.
- `core/tests/test_characters.py`
- `core/tests/test_api_characters.py`
- `core/tests/test_sessions_character_attach.py`
- `~/.claude/scripts/codetalker/characters/` (runtime; created on first save).

Reuse:
- `core/claude_code_talker/profiles.py` — pattern for ProfileStore; CharacterStore should be a near-clone with field renames.
- `core/claude_code_talker/triggers/skill.py::install_skill` — atomic-write pattern via tmp+rename.
- `core/claude_code_talker/api.py:_PROJECT_RE` — id validation regex template.

## Risks / open questions

- **`compose_skill_content` consumes persona**: today persona is read from `cfg.triggers.persona`. After 25a, the merged cfg's `triggers.persona` reflects character.persona when a character is attached. The change is mechanical (the merge layer takes care of it) — but the call sites in `api.py:1530` (`triggers_skill_install`) and `api.py:1546` (`triggers_skill_preview`) need to use the per-session merged cfg, not the global cfg. Verify during implementation; may already be correct.

- **Voice library coupling**: `voice_ref` is a string name. The voice library exposes voices via `engine.list_voices()` and `state.engines.<engine_name>` lookup. `attach-character` validation crosses these systems. Edge: if a voice is registered under engine "piper" but the cfg's default engine is "edge", does it still resolve? Probably yes, since voice_ref is a name not an `engine:name` tuple. But a future user could clone a voice in 25c that's only available on one engine. Document this in 25c when it lands.

- **Schema migration**: existing persistent session records don't have `attached_character`. The load path needs to default-fill it to `null`. PersistentSessionStore's deserialization code needs a one-line tolerance for missing field.

- **Backwards compat with VS Code extension**: the VS Code extension reads `/api/sessions` to build its session picker. Adding `attached_character` field is non-breaking; the extension can ignore it. Verify by reading the extension's session-list rendering after 25a lands.

- **Disk write contention**: if the user has 50+ characters and saves them in a tight loop (test scenario, not real use), the per-file atomic-write might be slow on Dropbox-synced filesystems (this project's working directory is Dropbox-synced). Mitigation: tests can mock the dir to a tmp path; production use won't hit this.

## Verification (end-to-end)

Once 25a is implemented:

1. `pytest core/tests/test_characters.py core/tests/test_api_characters.py core/tests/test_sessions_character_attach.py` — all new tests pass.
2. Full backend suite: `pytest core/tests/` — 856+ existing + ~25 new, all green.
3. Webui tests still green.
4. Manual: `curl -X POST http://127.0.0.1:17832/api/characters -d '{"id": "test-char", "display_name": "Test", "voice_ref": "en_GB-jenny_dioco-medium", "persona": "methodical"}'` returns the character with timestamps. File appears at `~/.claude/scripts/codetalker/characters/test-char.yaml`.
5. Manual: `curl -X POST http://127.0.0.1:17832/api/sessions/<sid>/attach-character -d '{"character_id": "test-char"}'` — session record reflects attached_character.
6. Manual: with character attached, prompt the session — narration uses character's voice (verified by listening, since the cfg merge changed `voice.model`).
7. Manual: detach, prompt again — narration falls back to profile or global voice.

## Success criteria for 25a

A developer can, with no UX:
1. POST a character via REST.
2. Attach it to a session via REST.
3. The session's narration uses the character's voice and persona.
4. Detach reverts cleanly.

When that's true, 25a is done and 25b/25c can build on it.
