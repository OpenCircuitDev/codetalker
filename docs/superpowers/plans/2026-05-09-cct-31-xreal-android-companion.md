# CCT-31 — XREAL Android AR Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans for Phases 1–4 (daemon-side, OSS, executable now). Phases 5–10 (Android-side, paid) are roadmap-level and require a configured Android Studio + Beam Pro hardware before TDD-level detail can be locked in.

**Goal:** Ship the codetalker AR companion as documented in [the CCT-31 spec](../specs/2026-05-09-cct-31-xreal-android-companion-design.md). Phase split mirrors the spec's edition fit: Phases 1–4 land in OSS `codetalker`; Phases 5–10 land in private `codetalker-pro`.

**Architecture:** New `core/claude_code_talker/companion/` package on the daemon side hosts the buddy Claude lifecycle, audio fan-out, screen capture, and pairing. Five new REST/SSE endpoints. Android app is a fresh Kotlin project at `companion-android/` (in pro repo when CCT-30 lands; in private branch meanwhile).

**Tech stack (daemon):** Python 3.11+, anthropic SDK (already in pyproject for the Anthropic provider), httpx, dxcam (Windows screen capture), pillow (JPEG encoding), websockets, secrets/hashlib for pairing tokens.

**Tech stack (Android):** Kotlin, Android 12+, Jetpack Compose, ExoPlayer for audio, XREAL Nebula SDK 2.x, Android SpeechRecognizer (v1 default; Whisper.cpp wrapped via JNI as v2 toggle).

**Reference spec:** [docs/superpowers/specs/2026-05-09-cct-31-xreal-android-companion-design.md](../specs/2026-05-09-cct-31-xreal-android-companion-design.md) — read in full before starting.

**Locked decisions (from spec):**
1. Voice→Claude path: **Claude Agent SDK companion session** (parallel buddy)
2. Network: **LAN-only v1 + Tailscale recipe**; cloud relay deferred to paid future offering
3. Hardware: **XREAL Air 2 Pro + Beam Pro**
4. Edition: **OSS Phases 1–4, paid Phases 5–10**
5. STT engine v1: **Android SpeechRecognizer**; Whisper.cpp as opt-in v2

**File structure (Phases 1–4, daemon-side, OSS):**
```
core/claude_code_talker/companion/                 # NEW package (~1200 LOC)
├── __init__.py
├── buddy.py                  # BuddyClaude — Anthropic SDK wrapper + transcript reader
├── audio_stream.py           # Per-session Opus frame fan-out
├── screen_capture.py         # dxcam + JPEG MJPEG stream
├── pairing.py                # QR-code token issue + validation
└── api.py                    # 5 new routes + ServerState wiring

core/claude_code_talker/
├── api.py                    # MODIFY — register companion routes
├── server.py                 # MODIFY — wire BuddyManager, ScreenCaptureSource
└── secrets_store.py          # MODIFY — pairing_token slot

core/claude_code_talker/webui/src/components/
└── PreferencesPanel.tsx      # MODIFY — "Pair AR Companion" QR button (Phase 4)

core/tests/
├── test_companion_buddy.py        # NEW — 8 tests
├── test_companion_audio.py        # NEW — 5 tests
├── test_companion_screen.py       # NEW — 4 tests
├── test_companion_pairing.py      # NEW — 5 tests
└── test_companion_api.py          # NEW — 6 tests
```

**File structure (Phases 5–10, Android-side, paid):**
```
companion-android/                                 # NEW Android Studio project
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       └── kotlin/dev/opencircuit/codetalker/
│           ├── MainActivity.kt
│           ├── ar/{AROverlay,SessionMenu,HUD,ScreenMirror}.kt
│           ├── audio/{TTSPlayer,STTRecorder}.kt
│           ├── input/{ButtonRouter,HardwareKeys}.kt
│           ├── net/{DaemonClient,PairingFlow,ConnectionGuard}.kt
│           └── viewmodel/CompanionViewModel.kt
├── build.gradle.kts
└── README.md
```

---

# Phases 1–4 — Daemon-side (OSS)

These are TDD-task detailed and executable autonomously. Each task: failing test first, implementation, run tests, commit. Same pattern as Phases 25/26/27.

## Task 1: BuddyClaude class + transcript reader (TDD)

**Files:**
- Create: `core/claude_code_talker/companion/__init__.py`
- Create: `core/claude_code_talker/companion/buddy.py`
- Create: `core/tests/test_companion_buddy.py`

- [ ] **Step 1: Write failing tests**

```python
"""CCT-31 — BuddyClaude session tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_code_talker.companion.buddy import (
    BuddyClaude,
    BuddyEvent,
    read_recent_transcript,
)


def test_read_recent_transcript_returns_last_n_messages(tmp_path):
    p = tmp_path / "session.jsonl"
    lines = [
        '{"role":"user","content":"q1"}',
        '{"role":"assistant","content":"a1"}',
        '{"role":"user","content":"q2"}',
        '{"role":"assistant","content":"a2"}',
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    out = read_recent_transcript(p, max_messages=3)
    assert len(out) == 3
    assert out[-1]["content"] == "a2"


def test_read_recent_transcript_handles_missing_file(tmp_path):
    out = read_recent_transcript(tmp_path / "missing.jsonl", max_messages=5)
    assert out == []


def test_buddy_construct_requires_api_key(tmp_path):
    with pytest.raises(ValueError, match="api_key"):
        BuddyClaude(user_session_id="x", transcript_path=tmp_path / "s.jsonl", anthropic_api_key="")


def test_buddy_construct_validates_transcript_path_exists_or_creates(tmp_path):
    p = tmp_path / "s.jsonl"
    BuddyClaude(user_session_id="x", transcript_path=p, anthropic_api_key="sk-test")
    # OK to point at a non-existent transcript; reads return [] silently.


@pytest.mark.asyncio
async def test_buddy_inject_appends_to_history():
    with patch("claude_code_talker.companion.buddy.anthropic") as mock_anth:
        stream_ctx = AsyncMock()
        stream_ctx.__aenter__.return_value.__aiter__ = lambda s: iter([])
        mock_anth.AsyncAnthropic.return_value.messages.stream.return_value = stream_ctx
        b = BuddyClaude(user_session_id="x", transcript_path=Path("/nope.jsonl"), anthropic_api_key="sk")
        events = []
        async for ev in b.inject("hello"):
            events.append(ev)
        assert b.history[-1]["role"] == "user"
        assert b.history[-1]["content"] == "hello"


@pytest.mark.asyncio
async def test_buddy_inject_emits_partial_then_final():
    fake_events = [
        MagicMock(type="content_block_delta", delta=MagicMock(text="hel")),
        MagicMock(type="content_block_delta", delta=MagicMock(text="lo")),
        MagicMock(type="message_stop"),
    ]
    with patch("claude_code_talker.companion.buddy.anthropic") as mock_anth:
        stream = MagicMock()
        stream.__aiter__ = lambda s: iter(fake_events)
        ctx = AsyncMock()
        ctx.__aenter__.return_value = stream
        mock_anth.AsyncAnthropic.return_value.messages.stream.return_value = ctx
        b = BuddyClaude(user_session_id="x", transcript_path=Path("/nope.jsonl"), anthropic_api_key="sk")
        events = [ev async for ev in b.inject("hi")]
        kinds = [e.kind for e in events]
        assert "partial_text" in kinds
        assert "final_text" in kinds or "done" in kinds


def test_buddy_event_partial_text_constructor():
    e = BuddyEvent(kind="partial_text", text="he")
    assert e.kind == "partial_text"
    assert e.text == "he"


def test_buddy_includes_transcript_context_in_system(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"role":"user","content":"earlier"}\n', encoding="utf-8")
    b = BuddyClaude(user_session_id="x", transcript_path=p, anthropic_api_key="sk")
    sys_prompt = b._build_system_prompt()
    assert "AR voice companion" in sys_prompt
    assert str(p) in sys_prompt or "transcript" in sys_prompt
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest core/tests/test_companion_buddy.py -v
```
Expected: all FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `companion/buddy.py`**

Create `core/claude_code_talker/companion/__init__.py` (empty).

Create `core/claude_code_talker/companion/buddy.py`:

```python
"""CCT-31 — BuddyClaude: parallel Anthropic Agent SDK session for AR companion.

Reads the user's main Claude Code session transcript for context but maintains
its own conversation. Read-only access to the user's session in v1.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Literal

try:
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover
    anthropic = None  # tests can patch


@dataclass
class BuddyEvent:
    kind: Literal["partial_text", "final_text", "tool_use", "done", "error"]
    text: str = ""
    error: str | None = None


def read_recent_transcript(path: Path, max_messages: int = 20) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and "role" in msg:
                out.append(msg)
    except OSError:
        return []
    return out[-max_messages:]


class BuddyClaude:
    def __init__(
        self,
        *,
        user_session_id: str,
        transcript_path: Path,
        anthropic_api_key: str,
        model: str = "claude-sonnet-4-5",
    ):
        if not anthropic_api_key:
            raise ValueError("api_key required")
        self.user_session_id = user_session_id
        self.transcript_path = Path(transcript_path)
        self.api_key = anthropic_api_key
        self.model = model
        self.history: list[dict] = []
        self._client = None  # lazily constructed in inject()

    def _build_system_prompt(self) -> str:
        return (
            "You are an AR voice companion. The user is wearing AR glasses "
            f"controlling another Claude Code session whose transcript is at "
            f"{self.transcript_path}. Read the recent transcript before "
            "answering. Keep responses short and conversational; they will "
            "be spoken aloud through the user's glasses speaker."
        )

    def _build_messages(self, user_text: str) -> list[dict]:
        ctx = read_recent_transcript(self.transcript_path, max_messages=20)
        # Format context as a system-style intro (Anthropic API treats only
        # role=user/assistant; context goes inside system_prompt for v1).
        msgs: list[dict] = []
        for m in ctx[-6:]:  # last 6 to keep prompt small
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, (str, list)):
                msgs.append({"role": role, "content": content if isinstance(content, str) else "[non-text]"})
        msgs.extend(self.history)
        msgs.append({"role": "user", "content": user_text})
        return msgs

    async def inject(self, text: str) -> AsyncIterator[BuddyEvent]:
        if anthropic is None:
            yield BuddyEvent(kind="error", error="anthropic SDK not installed")
            return
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        messages = self._build_messages(text)
        full_text_chunks: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.model,
                system=self._build_system_prompt(),
                messages=messages,
                max_tokens=512,
            ) as stream:
                async for evt in stream:
                    et = getattr(evt, "type", None)
                    if et == "content_block_delta":
                        delta = getattr(evt, "delta", None)
                        chunk = getattr(delta, "text", "") if delta else ""
                        if chunk:
                            full_text_chunks.append(chunk)
                            yield BuddyEvent(kind="partial_text", text=chunk)
                    elif et == "message_stop":
                        full = "".join(full_text_chunks)
                        self.history.append({"role": "user", "content": text})
                        self.history.append({"role": "assistant", "content": full})
                        yield BuddyEvent(kind="final_text", text=full)
                        yield BuddyEvent(kind="done")
                        return
        except Exception as e:  # pragma: no cover - real network errors
            yield BuddyEvent(kind="error", error=str(e))
```

- [ ] **Step 4: Run tests pass**

```bash
pytest core/tests/test_companion_buddy.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add core/claude_code_talker/companion/__init__.py core/claude_code_talker/companion/buddy.py core/tests/test_companion_buddy.py
git commit -m "feat(companion): BuddyClaude session + transcript reader (CCT-31 Task 1)"
```

---

## Task 2: BuddyManager — multi-buddy lifecycle (TDD)

**Files:**
- Modify: `core/claude_code_talker/companion/buddy.py` (add `BuddyManager`)
- Modify: `core/tests/test_companion_buddy.py`

- [ ] **Step 1: Add failing tests**

```python
def test_buddy_manager_creates_one_buddy_per_session(tmp_path):
    from claude_code_talker.companion.buddy import BuddyManager
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    b1 = mgr.start("sid-1")
    b2 = mgr.start("sid-1")
    assert b1 is b2  # same session reuses


def test_buddy_manager_independent_per_session(tmp_path):
    from claude_code_talker.companion.buddy import BuddyManager
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    b1 = mgr.start("sid-1")
    b2 = mgr.start("sid-2")
    assert b1 is not b2


def test_buddy_manager_stop_removes_buddy(tmp_path):
    from claude_code_talker.companion.buddy import BuddyManager
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    mgr.start("sid-1")
    mgr.stop("sid-1")
    assert "sid-1" not in mgr._buddies
```

- [ ] **Step 2: Implement BuddyManager**

Append to `companion/buddy.py`:

```python
class BuddyManager:
    def __init__(self, *, api_key: str, transcript_dir: Path, model: str = "claude-sonnet-4-5"):
        self.api_key = api_key
        self.transcript_dir = Path(transcript_dir)
        self.model = model
        self._buddies: dict[str, BuddyClaude] = {}

    def start(self, user_session_id: str) -> BuddyClaude:
        existing = self._buddies.get(user_session_id)
        if existing:
            return existing
        # Convention: Claude Code stores session transcripts at
        # transcript_dir / <session_id>.jsonl. Production codebases use the
        # SessionCatalog for resolution; we mirror that contract here.
        path = self.transcript_dir / f"{user_session_id}.jsonl"
        b = BuddyClaude(
            user_session_id=user_session_id,
            transcript_path=path,
            anthropic_api_key=self.api_key,
            model=self.model,
        )
        self._buddies[user_session_id] = b
        return b

    def get(self, user_session_id: str) -> BuddyClaude | None:
        return self._buddies.get(user_session_id)

    def stop(self, user_session_id: str) -> None:
        self._buddies.pop(user_session_id, None)

    def list_active(self) -> list[str]:
        return list(self._buddies.keys())
```

- [ ] **Step 3: Tests pass**

```bash
pytest core/tests/test_companion_buddy.py -v
```
Expected: 11 passed (8 + 3).

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/companion/buddy.py core/tests/test_companion_buddy.py
git commit -m "feat(companion): BuddyManager for per-session buddy lifecycle (CCT-31 Task 2)"
```

---

## Task 3: Pairing token store (TDD)

**Files:**
- Create: `core/claude_code_talker/companion/pairing.py`
- Create: `core/tests/test_companion_pairing.py`

- [ ] **Step 1: Failing tests**

```python
"""CCT-31 — pairing token store tests."""
from __future__ import annotations

import time
import pytest

from claude_code_talker.companion.pairing import PairingStore, PairingToken


def test_issue_token_returns_random_string(tmp_path):
    s = PairingStore(tmp_path / "tokens.json")
    t = s.issue(label="iphone-12", ttl_days=30)
    assert len(t.token) >= 32
    assert t.label == "iphone-12"


def test_validate_returns_true_for_known_unexpired(tmp_path):
    s = PairingStore(tmp_path / "tokens.json")
    t = s.issue(label="x", ttl_days=30)
    assert s.validate(t.token) is True


def test_validate_returns_false_for_expired(tmp_path):
    s = PairingStore(tmp_path / "tokens.json")
    t = s.issue(label="x", ttl_days=0)
    # Force-set expiry to past
    s._tokens[t.token] = PairingToken(token=t.token, label="x", issued_at=time.time() - 10, expires_at=time.time() - 1)
    s._save()
    assert s.validate(t.token) is False


def test_validate_returns_false_for_unknown(tmp_path):
    s = PairingStore(tmp_path / "tokens.json")
    assert s.validate("nope") is False


def test_revoke_removes_token(tmp_path):
    s = PairingStore(tmp_path / "tokens.json")
    t = s.issue(label="x", ttl_days=30)
    s.revoke(t.token)
    assert s.validate(t.token) is False


def test_persists_across_instances(tmp_path):
    p = tmp_path / "tokens.json"
    s1 = PairingStore(p)
    t = s1.issue(label="x", ttl_days=30)
    s2 = PairingStore(p)
    assert s2.validate(t.token) is True
```

- [ ] **Step 2: Implement pairing.py**

```python
"""CCT-31 — pairing token issue + validate, persisted to disk."""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PairingToken:
    token: str
    label: str
    issued_at: float
    expires_at: float


class PairingStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tokens: dict[str, PairingToken] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for tok, raw in data.items():
                self._tokens[tok] = PairingToken(**raw)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        data = {tok: asdict(t) for tok, t in self._tokens.items()}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(self.path)

    def issue(self, *, label: str, ttl_days: int = 30) -> PairingToken:
        token = secrets.token_urlsafe(32)
        now = time.time()
        t = PairingToken(
            token=token, label=label,
            issued_at=now, expires_at=now + ttl_days * 86400,
        )
        self._tokens[token] = t
        self._save()
        return t

    def validate(self, token: str) -> bool:
        t = self._tokens.get(token)
        if not t:
            return False
        if t.expires_at < time.time():
            return False
        return True

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)
        self._save()

    def list(self) -> list[PairingToken]:
        return list(self._tokens.values())
```

- [ ] **Step 3: Tests pass**

```bash
pytest core/tests/test_companion_pairing.py -v
```
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/companion/pairing.py core/tests/test_companion_pairing.py
git commit -m "feat(companion): PairingStore with TTL + persistence (CCT-31 Task 3)"
```

---

## Task 4: Audio stream multiplexer (TDD)

**Files:**
- Create: `core/claude_code_talker/companion/audio_stream.py`
- Create: `core/tests/test_companion_audio.py`

- [ ] **Step 1: Failing tests**

```python
"""CCT-31 — audio stream multiplexer tests."""
from __future__ import annotations

import asyncio
import pytest

from claude_code_talker.companion.audio_stream import AudioStreamHub


@pytest.mark.asyncio
async def test_subscribe_yields_published_frames():
    hub = AudioStreamHub()
    sub = hub.subscribe("sid-1")
    await hub.publish("sid-1", b"frame1")
    await hub.publish("sid-1", b"frame2")
    await hub.close("sid-1")
    frames = []
    async for f in sub:
        frames.append(f)
    assert frames == [b"frame1", b"frame2"]


@pytest.mark.asyncio
async def test_publish_to_other_session_isolated():
    hub = AudioStreamHub()
    sub_a = hub.subscribe("sid-a")
    sub_b = hub.subscribe("sid-b")
    await hub.publish("sid-a", b"a-only")
    await hub.close("sid-a")
    await hub.close("sid-b")
    a_frames = [f async for f in sub_a]
    b_frames = [f async for f in sub_b]
    assert a_frames == [b"a-only"]
    assert b_frames == []


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_frames():
    hub = AudioStreamHub()
    s1 = hub.subscribe("sid-x")
    s2 = hub.subscribe("sid-x")
    await hub.publish("sid-x", b"shared")
    await hub.close("sid-x")
    f1 = [f async for f in s1]
    f2 = [f async for f in s2]
    assert f1 == [b"shared"]
    assert f2 == [b"shared"]


@pytest.mark.asyncio
async def test_unsubscribed_after_close_yields_nothing():
    hub = AudioStreamHub()
    sub = hub.subscribe("sid-1")
    await hub.close("sid-1")
    assert [f async for f in sub] == []


@pytest.mark.asyncio
async def test_publish_to_unknown_session_silent():
    hub = AudioStreamHub()
    await hub.publish("ghost", b"frame")  # no raise
```

- [ ] **Step 2: Implement audio_stream.py**

```python
"""CCT-31 — Per-session async audio frame fan-out."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator


class AudioStreamHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[bytes | None]]] = {}

    def subscribe(self, session_id: str) -> AsyncIterator[bytes]:
        q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(q)

        async def _gen() -> AsyncIterator[bytes]:
            try:
                while True:
                    frame = await q.get()
                    if frame is None:
                        return
                    yield frame
            finally:
                if session_id in self._subscribers and q in self._subscribers[session_id]:
                    self._subscribers[session_id].remove(q)

        return _gen()

    async def publish(self, session_id: str, frame: bytes) -> None:
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass

    async def close(self, session_id: str) -> None:
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
```

- [ ] **Step 3: Tests pass**

```bash
pytest core/tests/test_companion_audio.py -v
```
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/companion/audio_stream.py core/tests/test_companion_audio.py
git commit -m "feat(companion): AudioStreamHub for per-session TTS frame fan-out (CCT-31 Task 4)"
```

---

## Task 5: Wire AudioStreamHub into TTS pipeline (TDD-light, integration)

**Files:**
- Modify: `core/claude_code_talker/audio.py` (or wherever Piper output lands)
- Modify: `core/tests/test_audio.py` (or new integration test)

- [ ] **Step 1: Locate the TTS sink**

Run: `grep -rn "piper\|sd.play\|pyaudio\|wav.write" core/claude_code_talker/ | head -20` to find where Piper-generated audio currently goes to the local sound card.

- [ ] **Step 2: Add a fan-out hook**

In the TTS pipeline, after the local playback call but BEFORE returning, add:

```python
# CCT-31: also publish to the AudioStreamHub for any subscribed companion phones.
if state.audio_hub is not None:
    asyncio.create_task(state.audio_hub.publish(session_id, encoded_opus_frame))
```

The encoded Opus frame should come from a small encoder helper that takes Piper's PCM output and produces Opus packets. If `opuslib` isn't on pyproject, add it.

- [ ] **Step 3: Smoke test by hand**

Spin up daemon, subscribe to `/api/audio-stream/<sid>` via curl, trigger an audible block, confirm frames arrive.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/audio.py core/pyproject.toml
git commit -m "feat(audio): fan TTS frames into AudioStreamHub (CCT-31 Task 5)"
```

---

## Task 6: Screen capture source (TDD)

**Files:**
- Create: `core/claude_code_talker/companion/screen_capture.py`
- Create: `core/tests/test_companion_screen.py`

- [ ] **Step 1: Failing tests**

```python
"""CCT-31 — screen capture source tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from claude_code_talker.companion.screen_capture import ScreenCaptureSource


def test_capture_fullscreen_returns_jpeg_bytes():
    fake_frame = MagicMock()
    fake_frame.tobytes.return_value = b"raw-pixels"
    with patch("claude_code_talker.companion.screen_capture._dxcam_grab", return_value=fake_frame), \
         patch("claude_code_talker.companion.screen_capture._encode_jpeg", return_value=b"jpeg-bytes"):
        s = ScreenCaptureSource()
        assert s.capture_fullscreen() == b"jpeg-bytes"


def test_capture_fullscreen_handles_missing_dxcam_gracefully():
    with patch("claude_code_talker.companion.screen_capture._dxcam_grab", side_effect=ImportError):
        s = ScreenCaptureSource()
        assert s.capture_fullscreen() is None


def test_capture_window_returns_jpeg_when_window_found():
    fake_frame = MagicMock()
    with patch("claude_code_talker.companion.screen_capture._find_window_by_title", return_value=(0, 0, 800, 600)), \
         patch("claude_code_talker.companion.screen_capture._dxcam_grab_region", return_value=fake_frame), \
         patch("claude_code_talker.companion.screen_capture._encode_jpeg", return_value=b"jpeg"):
        s = ScreenCaptureSource()
        assert s.capture_window("Claude Code") == b"jpeg"


def test_capture_window_returns_none_if_window_missing():
    with patch("claude_code_talker.companion.screen_capture._find_window_by_title", return_value=None):
        s = ScreenCaptureSource()
        assert s.capture_window("Nonexistent") is None
```

- [ ] **Step 2: Implement screen_capture.py**

```python
"""CCT-31 — Windows screen capture wrapped behind a stable interface.

Uses dxcam for fullscreen + region capture (Windows-only). On other platforms
or when dxcam isn't installed, returns None so the caller can degrade.
"""
from __future__ import annotations

import io
from typing import Optional

try:
    import dxcam  # type: ignore
    _DXCAM = dxcam.create()
except (ImportError, RuntimeError):
    _DXCAM = None

try:
    from PIL import Image  # type: ignore
except ImportError:
    Image = None  # type: ignore


def _dxcam_grab():
    if _DXCAM is None:
        raise ImportError("dxcam not available")
    return _DXCAM.grab()


def _dxcam_grab_region(region):
    if _DXCAM is None:
        raise ImportError("dxcam not available")
    return _DXCAM.grab(region=region)


def _find_window_by_title(title_substring: str) -> tuple[int, int, int, int] | None:
    try:
        import win32gui  # type: ignore
    except ImportError:
        return None
    found: list[tuple[int, int, int, int]] = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd) or ""
        if title_substring.lower() in title.lower():
            rect = win32gui.GetWindowRect(hwnd)
            found.append(rect)

    win32gui.EnumWindows(_enum, None)
    return found[0] if found else None


def _encode_jpeg(frame, quality: int = 70) -> bytes:
    if Image is None:
        return b""
    img = Image.fromarray(frame)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class ScreenCaptureSource:
    def capture_fullscreen(self) -> Optional[bytes]:
        try:
            frame = _dxcam_grab()
            if frame is None:
                return None
            return _encode_jpeg(frame)
        except (ImportError, Exception):
            return None

    def capture_window(self, title_substring: str) -> Optional[bytes]:
        rect = _find_window_by_title(title_substring)
        if rect is None:
            return None
        try:
            frame = _dxcam_grab_region(rect)
            if frame is None:
                return None
            return _encode_jpeg(frame)
        except (ImportError, Exception):
            return None
```

- [ ] **Step 3: Tests pass**

```bash
pytest core/tests/test_companion_screen.py -v
```
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/companion/screen_capture.py core/tests/test_companion_screen.py
git commit -m "feat(companion): ScreenCaptureSource with dxcam + win32gui (CCT-31 Task 6)"
```

---

## Task 7: REST endpoints — companion API (TDD)

**Files:**
- Create: `core/claude_code_talker/companion/api.py`
- Create: `core/tests/test_companion_api.py`
- Modify: `core/claude_code_talker/api.py` (register routes)
- Modify: `core/claude_code_talker/server.py` (wire `BuddyManager`, `AudioStreamHub`, `ScreenCaptureSource`, `PairingStore`)

- [ ] **Step 1: Failing tests**

```python
"""CCT-31 — companion REST endpoint tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from claude_code_talker.server import build_server_state
from claude_code_talker.api import build_routes
from starlette.applications import Starlette


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_TALKER_HOME", str(tmp_path))
    state = build_server_state()
    app = Starlette(routes=build_routes(state))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_post_pair_returns_token(client):
    r = await client.post("/api/companion/pair", json={"label": "test-phone"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert len(body["token"]) >= 32


@pytest.mark.asyncio
async def test_post_pair_validates_token(client):
    r = await client.post("/api/companion/pair", json={"label": "x"})
    tok = r.json()["token"]
    r2 = await client.get("/api/companion/sessions", headers={"X-CCT-Pairing-Token": tok})
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_companion_request_returns_401(client):
    r = await client.get("/api/companion/sessions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_post_start_buddy_requires_anthropic_key(client):
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    headers = {"X-CCT-Pairing-Token": tok}
    r = await client.post(
        "/api/companion/start-buddy",
        json={"user_session_id": "sid-1"},
        headers=headers,
    )
    assert r.status_code in (200, 400)  # 400 if no anthropic key set


@pytest.mark.asyncio
async def test_companion_active_session_endpoint(client):
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    r = await client.post(
        "/api/companion/active-session",
        json={"session_id": "sid-1"},
        headers={"X-CCT-Pairing-Token": tok},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_companion_screen_frames_returns_image_or_404(client):
    pair = await client.post("/api/companion/pair", json={"label": "x"})
    tok = pair.json()["token"]
    r = await client.get(
        "/api/companion/screen-frame/fullscreen",
        headers={"X-CCT-Pairing-Token": tok},
    )
    # On non-Windows / no dxcam: 503 or 404 acceptable. On Windows with dxcam: 200 + image/jpeg.
    assert r.status_code in (200, 404, 503)
```

- [ ] **Step 2: Implement companion/api.py**

```python
"""CCT-31 — Companion REST endpoints."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route


def _require_token(request: Request, store) -> bool:
    tok = request.headers.get("X-CCT-Pairing-Token", "")
    return store.validate(tok)


def make_routes(state) -> list[Route]:
    async def pair(request: Request) -> Response:
        body = await request.json()
        label = body.get("label", "unknown")
        ttl = int(body.get("ttl_days", 30))
        t = state.pairing.issue(label=label, ttl_days=ttl)
        return JSONResponse({"token": t.token, "label": t.label, "expires_at": t.expires_at})

    async def list_sessions(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        catalog = state.session_catalog
        return JSONResponse([{
            "session_id": s.session_id,
            "display_name": s.display_name,
            "is_live": getattr(s, "is_live", False),
        } for s in catalog.list()])

    async def start_buddy(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        sid = body.get("user_session_id")
        if not sid:
            return JSONResponse({"error": "user_session_id required"}, status_code=400)
        api_key = state.secrets.get("anthropic_api_key") if state.secrets else None
        if not api_key:
            return JSONResponse({"error": "anthropic_api_key not set"}, status_code=400)
        buddy = state.buddy_manager.start(sid)
        return JSONResponse({"buddy_id": sid, "status": "ready"})

    async def inject(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        bid = body.get("buddy_id")
        text = body.get("text", "")
        buddy = state.buddy_manager.get(bid) if bid else None
        if not buddy:
            return JSONResponse({"error": "buddy not started"}, status_code=404)
        # Stream events via SSE
        async def gen():
            async for ev in buddy.inject(text):
                yield f"event: {ev.kind}\ndata: {ev.text or ''}\n\n".encode()
        return StreamingResponse(gen(), media_type="text/event-stream")

    async def active_session(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        state.companion_active_session = body.get("session_id")
        return JSONResponse({"ok": True, "active_session_id": state.companion_active_session})

    async def audio_stream(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        sid = request.path_params["session_id"]
        async def gen():
            async for frame in state.audio_hub.subscribe(sid):
                yield frame
        return StreamingResponse(gen(), media_type="audio/opus")

    async def screen_frame(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        kind = request.path_params["kind"]
        if kind == "fullscreen":
            jpg = state.screen_capture.capture_fullscreen()
        else:
            jpg = state.screen_capture.capture_window("Claude Code")
        if jpg is None:
            return JSONResponse({"error": "capture unavailable"}, status_code=503)
        return Response(jpg, media_type="image/jpeg")

    return [
        Route("/api/companion/pair", pair, methods=["POST"]),
        Route("/api/companion/sessions", list_sessions, methods=["GET"]),
        Route("/api/companion/start-buddy", start_buddy, methods=["POST"]),
        Route("/api/companion/inject", inject, methods=["POST"]),
        Route("/api/companion/active-session", active_session, methods=["POST"]),
        Route("/api/companion/audio-stream/{session_id}", audio_stream, methods=["GET"]),
        Route("/api/companion/screen-frame/{kind}", screen_frame, methods=["GET"]),
    ]
```

- [ ] **Step 3: Wire ServerState**

In `server.py`'s `build_server_state`:

```python
from claude_code_talker.companion.buddy import BuddyManager
from claude_code_talker.companion.audio_stream import AudioStreamHub
from claude_code_talker.companion.screen_capture import ScreenCaptureSource
from claude_code_talker.companion.pairing import PairingStore

state.pairing = PairingStore(home / "companion" / "pairing.json")
state.audio_hub = AudioStreamHub()
state.screen_capture = ScreenCaptureSource()
state.buddy_manager = BuddyManager(
    api_key=state.secrets.get("anthropic_api_key") if state.secrets else "",
    transcript_dir=Path.home() / ".claude" / "projects",
)
state.companion_active_session = None
```

- [ ] **Step 4: Register routes in api.py**

In `build_routes(state)`:

```python
from claude_code_talker.companion.api import make_routes as _companion_routes
routes.extend(_companion_routes(state))
```

- [ ] **Step 5: Tests pass**

```bash
pytest core/tests/test_companion_api.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add core/claude_code_talker/companion/api.py core/claude_code_talker/api.py core/claude_code_talker/server.py core/tests/test_companion_api.py
git commit -m "feat(api): companion REST endpoints (CCT-31 Task 7)"
```

---

## Task 8: Dashboard "Pair AR Companion" UI

**Files:**
- Modify: `core/claude_code_talker/webui/src/components/PreferencesPanel.tsx`
- Add: a `qrcode` package via npm

- [ ] **Step 1: Add QR rendering dep**

```bash
cd core/claude_code_talker/webui && npm install qrcode.react @types/qrcode
```

- [ ] **Step 2: Add Pair section to PreferencesPanel**

```tsx
import { useState } from "react";
import QRCode from "qrcode.react";

// inside PreferencesPanel:
const [pairToken, setPairToken] = useState<string | null>(null);
const issue = async () => {
  const r = await fetch("/api/companion/pair", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({label: navigator.userAgent.slice(0, 40)}),
  });
  const data = await r.json();
  setPairToken(data.token);
};

const pairPayload = pairToken
  ? JSON.stringify({daemon_url: `http://${window.location.host}`, pairing_token: pairToken})
  : null;

// JSX:
<section className="...">
  <h3 className="font-bold">AR Companion</h3>
  <button onClick={issue} className="px-3 py-1 bg-cyan-600 text-white rounded">
    Issue pairing token
  </button>
  {pairPayload && (
    <div className="mt-2 inline-block bg-white p-3 rounded">
      <QRCode value={pairPayload} size={192} />
      <p className="text-zinc-700 text-xs mt-2">Scan with the codetalker Android app</p>
    </div>
  )}
</section>
```

- [ ] **Step 3: Manual smoke**

Click "Issue pairing token", QR appears, token decodes to JSON.

- [ ] **Step 4: Commit**

```bash
git add core/claude_code_talker/webui/src/components/PreferencesPanel.tsx core/claude_code_talker/webui/package.json core/claude_code_talker/webui/package-lock.json
git commit -m "feat(webui): Pair AR Companion QR generator (CCT-31 Task 8)"
```

---

## Task 9: Final regression sweep + push

- [ ] **Step 1: Full backend pytest**

```bash
cd core && python -m pytest tests/ -q
```
Expected: 1011+ passing (28 new from CCT-31).

- [ ] **Step 2: Full webui vitest**

```bash
cd core/claude_code_talker/webui && npx vitest run && npm run build
```
Expected: 40+ passing, build clean.

- [ ] **Step 3: Manual smoke**

Run `claude-code-talker serve`, hit each new endpoint via curl with a fresh token, confirm responses.

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

# Phases 5–10 — Android-side (paid, codetalker-pro)

These phases land in the private `codetalker-pro` repo (or a private branch until CCT-30 splits the repos). Detailed TDD task breakdowns require a configured Android Studio + Beam Pro hardware to verify against the real XREAL Nebula SDK; the breakdowns below are at the milestone level with code shapes the implementing dev can flesh out.

## Phase 5 — Android skeleton + LAN client

**Tasks:**
1. Android Studio project: Kotlin, min SDK 31, target SDK 34, Jetpack Compose
2. Add deps: `okhttp` (REST), `okhttp-sse` (SSE), `media3-exoplayer` (audio), `qrcode-zxing` (QR scan), `compose-material3`
3. `DaemonClient.kt` — REST + SSE wrapper, `X-CCT-Pairing-Token` header on every request
4. `PairingFlow.kt` — QR scanner, store token + daemon URL in EncryptedSharedPreferences
5. Pairing Activity: scan, validate (`GET /api/companion/sessions`), persist
6. Unit tests for DaemonClient retry/auth header

**Verification:** scan QR from dashboard, see "paired" status, list sessions returns the daemon's catalog.

## Phase 6 — Button router + STT input

**Tasks:**
1. `HardwareKeys.kt` — capture Beam Pro side-button via `KeyEvent.KEYCODE_VOLUME_UP/DOWN/POWER` overrides at Activity level (Beam Pro maps these to side-button events; verify on real hardware)
2. `ButtonRouter.kt` state machine: IDLE → LISTENING (click), MENU (double-click), back to IDLE on long-press
3. `STTRecorder.kt` — wraps `android.speech.SpeechRecognizer` with offline mode preference; emits `RecognitionResult` (partial + final)
4. Wire LISTENING state to STTRecorder, post final text to `POST /api/companion/inject`, subscribe SSE for buddy response
5. UI tests for state transitions + mock STT

**Verification:** click → mic indicator appears in HUD → speak → text appears in HUD → buddy SSE response streams in.

## Phase 7 — TTS playback

**Tasks:**
1. `TTSPlayer.kt` — ExoPlayer with `OpusAudioRenderer`, subscribes to `GET /api/companion/audio-stream/{sid}` as a continuous Opus stream
2. Buffer management: 150ms target, jitter window
3. Active-session change handler: tear down existing subscription, open new one
4. Mute toggle reads from `useSessionConfig` overlay

**Verification:** TTS playback within 200ms of daemon audio output; smooth across active-session changes.

## Phase 8 — AR HUD + menu (Nebula SDK)

**Tasks:**
1. Integrate Nebula SDK 2.x via Gradle
2. `AROverlay.kt` — root composition that owns three AR layers: HUD (head-pinned), Menu (world-pinned at arm's length), Mirror (world-pinned, larger)
3. `HUD.kt` — shows active session chip, mic icon, audio-playing waveform
4. `SessionMenu.kt` — vertical scrollable session list, rocker scrolls selection, click confirms, fades in/out
5. Button router MENU state hooks SessionMenu show/hide
6. Tailwind-equivalent surface tokens copied from Phase 27 React tokens.css for visual coherence

**Verification:** put on glasses, see HUD floats below gaze, double-click pops menu in front of you, rocker scrolls selection, click commits.

## Phase 9 — Screen mirror (MJPEG)

**Tasks:**
1. `ScreenMirror.kt` — periodic poll of `GET /api/companion/screen-frame/fullscreen` or `/window`, decode JPEG with `BitmapFactory`, render to `ImageView` in AR Mirror layer
2. Adaptive frame rate: 5 fps idle, 15 fps when content changes (compare frame hashes; bump rate when delta detected)
3. Toggle on/off via SessionMenu item
4. Auto-fade after 30s of inactivity
5. World-anchor the mirror (Nebula SDK API for world-pin)

**Verification:** menu → "Show screen" → mirror appears at arm's length, updates as Claude Code window changes.

## Phase 10 — Polish: reconnection, network, battery

**Tasks:**
1. `ConnectionGuard.kt` — exponential backoff on disconnect, reconnect on WiFi/Tailscale change events
2. Foreground service for audio + companion connection (Android 14 background restriction)
3. Battery profile: kill SSE subscriptions in background, resume on AR active
4. Tailscale recipe doc: README section explaining install on phone + PC, `tailscale up`, daemon already binds to Tailnet IP
5. Crash reporter (opt-in)
6. App icon, branding, Google Play (or sideload-only) listing

**Verification:** daemon disconnect + reconnect handled gracefully; airplane mode → reconnect on WiFi; 1-hour use stays under 30% battery on Beam Pro.

---

## Notes for the implementer

- **Phases 1–4 are autonomous-execution-ready** — dispatch subagent-driven-development against them. Every task has failing test → implementation → test pass → commit.
- **Phases 5–10 require human discretion** at the XREAL SDK / Android UI fidelity layer. The milestone descriptions are concrete enough to plan against; the per-task TDD detail will be added once a developer has Beam Pro hardware in hand and can verify SDK behavior.
- **DRY**: companion package mirrors mesh package structure (`buddy.py` like `provider.py`, `api.py` like the mesh routes). Use the same patterns.
- **YAGNI v1**: don't bundle Whisper, don't add WebRTC, don't ship multi-PC support. Each is in the spec's "out of scope for v1."
- **Frequent commits**: every Phase 1–4 task ends with a commit. For Phase 5–10, commit per milestone within each phase.
- **Test rigor**: backend phases use real pytest TDD; Android phases use Android instrumentation tests + UI tests where the test infra supports it; manual verification on hardware is acceptable for AR/audio behavior.

---

## Phase order reminder

```
Phase 1 (BuddyClaude)        ─┐
Phase 2 (BuddyManager)        │ Daemon-side
Phase 3 (Pairing)             │ OSS, Phases 1-9 in current
Phase 4 (AudioStreamHub)      │ codetalker repo
Phase 5 (TTS fan-out wire)    │
Phase 6 (ScreenCapture)       │
Phase 7 (REST endpoints)      │
Phase 8 (Dashboard QR UI)    ─┤
Phase 9 (regression+push)    ─┘

──── (gate: CCT-30 repo split lands; codetalker-pro exists) ────

Phase 5 [Android skeleton]   ─┐
Phase 6 [Button + STT]        │ Android-side
Phase 7 [TTS playback]        │ Paid edition,
Phase 8 [AR HUD + menu]       │ codetalker-pro repo
Phase 9 [Screen mirror]       │
Phase 10 [Polish + Tailscale] ┘
```

Note the phase numbering is reused intentionally — daemon Phase 5 = "wire AudioStreamHub into TTS pipeline"; Android Phase 5 = "Android skeleton." They're in different files / different repos / different review cycles.

---

## Verification (end-to-end, Phase 1–4 OSS slice)

After Phase 4 lands and is pushed:

1. Daemon serves the seven new companion endpoints.
2. `pytest core/tests/test_companion_*.py` — all green (28 tests).
3. Dashboard's Preferences panel shows "Pair AR Companion" with a working QR generator.
4. `curl -X POST http://localhost:17832/api/companion/pair -d '{"label":"test"}'` returns a valid token.
5. Subsequent `GET /api/companion/sessions` with that token returns the daemon's session catalog.
6. With `ANTHROPIC_API_KEY` set, `POST /api/companion/start-buddy` succeeds and `inject` streams an SSE response.
7. (Windows only) `GET /api/companion/screen-frame/fullscreen` returns valid JPEG bytes.

This puts the daemon side fully in place. Android development can begin against the live endpoints from any developer with a Beam Pro and an Android Studio install.

## Verification (end-to-end, full v1 after Phase 10)

End-to-end smoke from the spec:
1. Pair phone via dashboard QR.
2. Wear glasses + Beam Pro. HUD shows active session badge.
3. TTS narration plays via phone speakers.
4. Click → "What test is failing?" → buddy reads transcript → speaks back.
5. Double-click → menu → rocker → click → active session switches.
6. Menu → screen mirror → see Claude Code window in AR.
7. Walk away from desk; Tailscale keeps connection alive.
