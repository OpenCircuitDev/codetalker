"""CCT-31 — Companion REST endpoints.

These routes power the XREAL Android AR companion app. Every endpoint other
than `/api/companion/pair` requires the X-CCT-Pairing-Token header set to a
token previously issued by this daemon.
"""
from __future__ import annotations

import asyncio
import socket

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from claude_code_talker.daemon import DAEMON_PORT


def _require_token(request: Request, store) -> bool:
    tok = request.headers.get("X-CCT-Pairing-Token", "")
    return store.validate(tok)


async def _send_keys_to_foreground(text: str) -> None:
    """Type `text` into the OS foreground window, then press Enter.

    Windows-only — uses PowerShell + System.Windows.Forms.SendKeys. The
    user is expected to have their Claude Code session window focused on
    the desktop before triggering the direct-STT gesture; this function
    does not raise or switch window focus.

    SendKeys treats `+`, `^`, `%`, `~`, `{`, `}`, `(`, `)`, `[`, `]` as
    modifier/grouping characters; we escape each by wrapping in braces
    (e.g. `+` → `{+}`). Newlines in the transcript map to Enter via the
    final `~` sentinel after the text.
    """
    import asyncio
    import subprocess
    import sys
    if sys.platform != "win32":
        raise RuntimeError(
            f"direct-STT keyboard injection is Windows-only; got {sys.platform}"
        )
    # Escape SendKeys metacharacters. Order matters — braces first so we
    # don't double-escape the wrapper braces below.
    escape_map = [
        ("{", "{{}"),
        ("}", "{}}"),
        ("+", "{+}"),
        ("^", "{^}"),
        ("%", "{%}"),
        ("~", "{~}"),
        ("(", "{(}"),
        (")", "{)}"),
        ("[", "{[}"),
        ("]", "{]}"),
    ]
    escaped = text
    for src, dst in escape_map:
        escaped = escaped.replace(src, dst)
    # PowerShell's own quoting — wrap the escaped text in single quotes and
    # double any internal single quotes per PS literal-string rules.
    ps_literal = escaped.replace("'", "''")
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Start-Sleep -Milliseconds 150;"
        f"[System.Windows.Forms.SendKeys]::SendWait('{ps_literal}');"
        # Final Enter — `~` is SendKeys' literal for Enter.
        "[System.Windows.Forms.SendKeys]::SendWait('~')"
    )
    # CREATE_NO_WINDOW = 0x08000000 keeps the PS window from flashing.
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script,
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("SendKeys subprocess timed out after 10s")
    if proc.returncode != 0:
        err = (stderr or b"").decode(errors="replace")[:500]
        raise RuntimeError(f"SendKeys failed (exit {proc.returncode}): {err}")


# 2026-05-16 -- delegate to the single canonical implementation in
# api.py so the two surfaces NEVER drift. Previously this file held a
# copy that had to be hand-mirrored every time a new project family was
# added; the next "showing as Ungrouped on phone but grouped on web"
# bug was effectively guaranteed under that pattern.
from claude_code_talker.api import _derive_workspace_group  # noqa: F401


def _best_reachable_url(port: int = DAEMON_PORT) -> str:
    """Return the URL a phone on the same LAN/Tailnet should use to reach
    this daemon.

    The dashboard's Pair AR Companion QR was previously using
    ``window.location.host`` which encoded whatever URL the user had the
    dashboard open at — typically loopback ``127.0.0.1`` — and the phone
    then dialed loopback (= itself), getting connection refused.

    This helper sidesteps that by asking the OS which interface address it
    would use to reach the public internet. The connect() call against
    8.8.8.8 doesn't actually send anything; UDP socket setup just resolves
    the routing table to pick a source IP. That IP is the LAN address
    (or Tailnet address if Tailscale is the default route to that target).
    Falls back to loopback only when no network is reachable.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return f"http://{ip}:{port}"
        finally:
            s.close()
    except Exception:
        return f"http://127.0.0.1:{port}"


def _ensure_phone_in_audio_outputs(state, sid: str) -> None:
    """Append "phone" to a session's persisted audio_outputs if missing.

    2026-05-16 — without this, marking a session active from the phone
    has no audible effect. The audio worker's Strategy-C router (audio.py)
    filters opted-in destinations from each session's audio_outputs and
    drops the synthesized WAV silently when "phone" is absent. The default
    for a new Session is ["desktop"] only (schemas/session.py), so the
    grant must fire explicitly when the phone subscribes.

    Idempotent — no-op when "phone" is already present, when the persistent
    store isn't initialized, or when sid is empty. Routes through
    _merge_into_persistent so the write follows the same validation
    (allowlist + sort + dedupe) as a webui PATCH, and emits SessionChanged
    so the webui's SSE subscribers see the row update without waiting
    for the next 30s poll.

    Sticky by design: removing a session from the active set does NOT
    strip "phone". A user who explicitly wants phone-off for a session
    can do so from the audio sinks UI; auto-grant should never feel
    like it's fighting the user's explicit choice.
    """
    if not sid or state.persistent_sessions is None:
        return
    existing = state.persistent_sessions.get(sid) or {}
    # 2026-05-17 — when audio_outputs is missing from the persistent dict,
    # default to the Session schema default ["desktop"] rather than [].
    # The legacy adapter's session_to_legacy_dict OMITS the field when
    # it equals the default to save bytes, so a freshly-created session
    # (which has audio_outputs=["desktop"]) shows up here as missing.
    # Treating missing as [] caused this function to overwrite it with
    # ["phone"] only — silently destroying desktop fallback and leaving
    # the user with no audio whenever the phone subscriber was briefly
    # missing. THIS is the multi-day silence root cause.
    current = existing.get("audio_outputs")
    if not isinstance(current, (list, tuple)) or not current:
        current = ["desktop"]
    if "phone" in current:
        return
    new_outputs = list(current) + ["phone"]
    from claude_code_talker.api import _merge_into_persistent, _emit_session_changed
    try:
        _merge_into_persistent(state, sid, {"audio_outputs": new_outputs})
    except Exception:
        return
    _emit_session_changed(state, sid, {"audio_outputs": new_outputs})


def make_routes(state) -> list[Route]:
    async def pair(request: Request) -> Response:
        body = await request.json()
        label = body.get("label", "unknown")
        ttl = int(body.get("ttl_days", 30))
        t = state.pairing.issue(label=label, ttl_days=ttl)
        # CCT-31: include the daemon URL the dashboard's QR generator
        # should encode. Server-side resolution avoids the loopback-trap
        # that bites when a user has the dashboard open at
        # http://127.0.0.1:17832 — window.location.host would put loopback
        # in the QR, the phone would dial its own loopback, and the
        # pairing would silently fail. The server knows the right answer.
        return JSONResponse({
            "token": t.token,
            "label": t.label,
            "expires_at": t.expires_at,
            "daemon_url": _best_reachable_url(),
        })

    async def list_sessions(request: Request) -> Response:
        """GET /api/companion/sessions — Pro Android session list.

        Phase 3 (2026-05-16): row construction delegated to the shared
        `views.build_session_view` so this endpoint emits the same
        SessionView shape as the webui-facing /api/sessions. The only
        companion-specific work is auth (pairing-token gate) and
        passing the companion_active_sessions set so rows carry
        is_companion_active=True for the right sid.
        """
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        catalog = state.catalog
        if catalog is None:
            return JSONResponse([])

        live_by_sid: dict[str, object] = {}
        try:
            for s in (state.sessions.list_active() if state.sessions else []):
                live_by_sid[s.session_id] = s
        except AttributeError:
            pass

        # Multi-active aware: companion_active_sessions is a set; fall
        # back to the legacy single-slot field for old callers that
        # haven't migrated.
        active_sids = getattr(state, "companion_active_sessions", None) or set()
        if not active_sids:
            legacy = getattr(state, "companion_active_session", None)
            if legacy:
                active_sids = {legacy}

        import time as _t
        from claude_code_talker.views import (
            SESSION_VISIBILITY_WINDOW_SEC,
            build_session_view,
        )

        _now = _t.time()
        visible_entries = [
            e for e in catalog.entries()
            if (_now - getattr(e, "last_modified", 0.0)) < SESSION_VISIBILITY_WINDOW_SEC
        ]

        # 2026-05-17 — per-row exception handling. Previously one bad
        # session (e.g. a persistent overlay with a value that failed
        # Pydantic SessionView validation, or a corrupted live_match
        # after a PATCH) crashed the entire endpoint with HTTP 500.
        # User reported "ANY time I change any session setting, my
        # sessions disappear" — the underlying cause: the PATCH
        # succeeded server-side but the next list_sessions call
        # blew up on the bad row, hiding ALL rows. With this guard
        # the bad row is skipped and logged; the rest of the list
        # returns normally. The exception is logged at ERROR so the
        # daemon log surfaces which sid + which error triggered it.
        views = []
        failed: list[tuple[str, str]] = []
        seen: set[str] = set()
        for e in visible_entries:
            sid = e.session_id
            seen.add(sid)
            try:
                persistent = (
                    state.persistent_sessions.get(sid)
                    if state.persistent_sessions is not None
                    else None
                )
                views.append(build_session_view(
                    state,
                    sid,
                    live_match=live_by_sid.get(sid),
                    catalog_entry=e,
                    persistent=persistent,
                    companion_active_sids=active_sids,
                ))
            except Exception as exc:
                import logging as _log
                _log.error(
                    "CCT-API: list_sessions skipped sid=%s: %s: %s",
                    sid[:12], type(exc).__name__, str(exc)[:200],
                )
                failed.append((sid, f"{type(exc).__name__}: {str(exc)[:120]}"))
        # Sessions that are live but not yet in the catalog (newly spawned).
        for sid, live_match in live_by_sid.items():
            if sid in seen:
                continue
            try:
                persistent = (
                    state.persistent_sessions.get(sid)
                    if state.persistent_sessions is not None
                    else None
                )
                views.append(build_session_view(
                    state,
                    sid,
                    live_match=live_match,
                    persistent=persistent,
                    companion_active_sids=active_sids,
                ))
            except Exception as exc:
                import logging as _log
                _log.error(
                    "CCT-API: list_sessions skipped (live-only) sid=%s: %s: %s",
                    sid[:12], type(exc).__name__, str(exc)[:200],
                )
                failed.append((sid, f"{type(exc).__name__}: {str(exc)[:120]}"))
        try:
            return JSONResponse([v.model_dump(mode="json") for v in views])
        except Exception as exc:
            # Serialization itself failed — surface that distinctly so the
            # next debugging cycle sees "the views built but couldn't
            # serialize" vs. "build_session_view raised on every row."
            import logging as _log
            _log.error(
                "CCT-API: list_sessions serialization failed (built %d views, %d failed earlier): %s",
                len(views), len(failed), exc,
            )
            return JSONResponse(
                {"error": f"serialization: {type(exc).__name__}: {str(exc)[:200]}"},
                status_code=500,
            )

    async def start_buddy(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        sid = body.get("user_session_id")
        if not sid:
            return JSONResponse({"error": "user_session_id required"}, status_code=400)
        # CCT-32 v0.1.0 polish — buddy is OpenRouter-first; fall back to a
        # direct Anthropic key if that's what the user has configured.
        api_key = None
        if state.secrets is not None:
            api_key = (
                state.secrets.get("openrouter_api_key")
                or state.secrets.get("anthropic_api_key")
            )
        if not api_key:
            return JSONResponse(
                {"error": "openrouter_api_key (or anthropic_api_key) not set in secrets"},
                status_code=400,
            )
        # Re-create the BuddyManager with the live key if it was constructed
        # before the key was persisted (covers first-run boot order).
        if not getattr(state.buddy_manager, "api_key", None):
            state.buddy_manager.api_key = api_key
        state.buddy_manager.start(sid)
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
        # v0.1.0 unification — STT-driven inject counts as user interaction
        # so auto-mode flips the session into "live" while the user is
        # actively chatting through the AR companion.
        try:
            import time as _t
            from claude_code_talker.sessions import evaluate_auto_mode
            _bsid = body.get("buddy_id") or ""
            if _bsid and state.sessions is not None:
                _bs = state.sessions.get(_bsid)
                if _bs is not None:
                    _bs.last_user_interaction_at = _t.time()
                evaluate_auto_mode(state, _bsid)
        except Exception:
            pass
        # CCT-32 v0.1.0 polish — capture the buddy's final text and route it
        # through the local TTS pipeline so the companion's audio-stream
        # subscriber actually receives synthesized speech. Without this, the
        # AR companion would see captions but hear silence.
        #
        # 2026-05-16 root-cause fix — was using `companion_active_session
        # OR bid` to tag the audio job. When CAS is set to a sid that has
        # NO audio_outputs configured (a freshly-spawned session, or one
        # the user explicitly cleared), the audio worker's Strategy-C
        # router sees `job_session_id NOT in opted_in_sessions` and drops
        # the WAV silently. Using `bid` (the buddy's own session, which
        # is the user_session_id the user explicitly invoked) ensures
        # job.session_id is a real, opted-in session. Strategy C will
        # still fan the audio into CAS's hub key when CAS is set;
        # that's a separate concern handled inside the routing strategy.
        audio_source_sid = bid

        async def gen():
            final_text = ""
            async for ev in buddy.inject(text):
                if ev.kind == "final_text":
                    final_text = ev.text or ""
                yield f"event: {ev.kind}\ndata: {ev.text or ''}\n\n".encode()
            # After the SSE stream completes, hand the final reply to the
            # AudioQueue. The worker synthesizes via Piper (or whatever engine
            # the session resolves to) and publishes Opus frames to audio_hub
            # keyed by session_id — exactly what /api/companion/audio-stream
            # subscribes to.
            if final_text and getattr(state, "audio_queue", None) is not None:
                try:
                    from claude_code_talker.audio import AudioJob
                    cfg = {}
                    if state.sessions is not None and audio_source_sid:
                        try:
                            cfg = state.sessions.config_for(audio_source_sid)
                        except Exception:
                            cfg = {}
                    voice_cfg = cfg.get("voice") or {}
                    engine_name = voice_cfg.get("engine") or "piper"
                    engine = state.engines.get(engine_name) if state.engines else None
                    voice = voice_cfg.get("model")
                    if engine is not None:
                        state.audio_queue.submit(AudioJob(
                            text=final_text,
                            voice=voice or "",
                            rate=float(voice_cfg.get("rate", 1.0)),
                            engine_name=engine_name,
                            audio_format=getattr(engine, "audio_format", "wav"),
                            session_id=audio_source_sid or "",
                        ))
                except Exception:
                    # Audio fan-out must not break the SSE response path.
                    pass

        return StreamingResponse(gen(), media_type="text/event-stream")

    async def active_session(request: Request) -> Response:
        """POST /api/companion/active-session

        2026-05-11 — promoted from a single-slot setter to a multi-active
        toggle. Body shape:
          - {"session_id": "...", "active": true}   add to set
          - {"session_id": "...", "active": false}  remove from set
          - {"session_id": "..."}                   legacy: equivalent to
                                                    active=true; also clears
                                                    other members so single-
                                                    slot callers see the old
                                                    behavior. Pass an empty
                                                    string + active=false to
                                                    clear the whole set.

        The legacy `companion_active_session` field is kept in sync to "the
        primary" member so audio.py's _companion_owns_audio + buddy.py keep
        working without changes.
        """
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        sid = (body.get("session_id") or "").strip()
        # 2026-05-16 — snapshot the active set BEFORE mutation so we can
        # detect which sids were newly added and auto-grant phone audio
        # to exactly those (idempotent for sids that were already active).
        prior_active: set = set(getattr(state, "companion_active_sessions", None) or set())
        if "active" in body:
            active = bool(body.get("active"))
            current: set = getattr(state, "companion_active_sessions", None) or set()
            if active and sid:
                current.add(sid)
            elif sid:
                current.discard(sid)
            else:
                current.clear()
            state.companion_active_sessions = current
        else:
            # Legacy single-slot: replace the entire set with this one sid.
            state.companion_active_sessions = {sid} if sid else set()
        # Keep the legacy field pointing at one member (arbitrary but
        # deterministic — first by lex order) so audio.py's check is stable.
        sids_sorted = sorted(state.companion_active_sessions)
        state.companion_active_session = sids_sorted[0] if sids_sorted else None
        # 2026-05-16 — for every sid the phone just marked active that
        # wasn't already active, ensure "phone" is in its persisted
        # audio_outputs. Without this the audio worker drops the WAV
        # silently because the session isn't an opted-in phone destination.
        # See _ensure_phone_in_audio_outputs for the sticky-grant rationale.
        for added_sid in state.companion_active_sessions - prior_active:
            _ensure_phone_in_audio_outputs(state, added_sid)
        # 2026-05-16 (Option C bidirectional sync) — emit
        # CompanionActiveSessionsChanged so every connected client mirrors
        # the canonical set immediately. Replaces the brittle one-shot
        # reconciliation that kept getting stale across daemon restarts +
        # transient network blips. The originating client receives its own
        # echo (idempotent — applying the same set is a no-op).
        if state.companion_active_sessions != prior_active:
            bus = getattr(state, "event_bus", None)
            if bus is not None:
                try:
                    from claude_code_talker.schemas import CompanionActiveSessionsChanged
                    import time as _t
                    bus.publish_threadsafe(CompanionActiveSessionsChanged(
                        at=_t.time(),
                        active_session_ids=sids_sorted,
                    ))
                except Exception:
                    pass
        return JSONResponse({
            "ok": True,
            "active_session_id": state.companion_active_session,
            "active_session_ids": sids_sorted,
        })

    async def active_sessions_list(request: Request) -> Response:
        """GET /api/companion/active-sessions — returns the full set so the
        phone can rehydrate after process death or pair from a 2nd device."""
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        sids_sorted = sorted(getattr(state, "companion_active_sessions", set()) or set())
        return JSONResponse({"active_session_ids": sids_sorted})

    async def audio_stream(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        sid = request.path_params["session_id"]
        # v0.1.0 polish — long-poll for one WAV at a time and return it as a
        # complete bounded Response (with Content-Length, no chunked
        # encoding). The original StreamingResponse held the connection open
        # forever, which left ExoPlayer's WAV decoder waiting for an EOF that
        # never arrived, so playback stalled despite valid bytes flowing.
        # Client (Android TTSPlayer) re-calls this endpoint on
        # Player.STATE_ENDED to fetch the next WAV. 204 No Content is
        # returned when nothing publishes within the long-poll window so the
        # client knows to retry without errors.
        gen = state.audio_hub.subscribe(sid)
        try:
            try:
                frame = await asyncio.wait_for(gen.__anext__(), timeout=55.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                return Response(status_code=204)
        finally:
            try:
                await gen.aclose()
            except Exception:
                pass
        return Response(content=frame, media_type="audio/wav")

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

    async def direct_stt(request: Request) -> Response:
        """2026-05-12 — direct-STT entry point.

        Phone's vol-UP long-press records audio, transcribes (phone-side or
        via daemon STT pipeline), and POSTs the result here. The daemon
        types the transcript via Windows SendKeys into whatever has OS
        focus on the desktop — presumed to be the user's Claude Code
        window for the session named in `session_id`. (Daemon does NOT
        switch window focus; the user keeps their CC window foreground
        while triggering the gesture.)

        This is intentionally distinct from `/api/companion/inject`, which
        routes through the Buddy LLM intermediate. Direct-STT bypasses
        Buddy entirely and lands the words straight into the running CC
        session's user-input pipeline.

        Body: {"text": "...", "session_id": "..."}
        Returns: {"ok": true, "session_id": ..., "chars": N}
                 or {"error": ...} on failure.
        """
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        text = (body.get("text") or "").strip()
        session_id = body.get("session_id") or ""
        if not text:
            return JSONResponse({"error": "text required"}, status_code=400)
        try:
            await _send_keys_to_foreground(text)
            return JSONResponse({
                "ok": True,
                "session_id": session_id,
                "chars": len(text),
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    return [
        Route("/api/companion/pair", pair, methods=["POST"]),
        Route("/api/companion/sessions", list_sessions, methods=["GET"]),
        Route("/api/companion/start-buddy", start_buddy, methods=["POST"]),
        Route("/api/companion/inject", inject, methods=["POST"]),
        Route("/api/companion/direct-stt", direct_stt, methods=["POST"]),
        Route("/api/companion/active-session", active_session, methods=["POST"]),
        Route("/api/companion/active-sessions", active_sessions_list, methods=["GET"]),
        Route("/api/companion/audio-stream/{session_id}", audio_stream, methods=["GET"]),
        Route("/api/companion/screen-frame/{kind}", screen_frame, methods=["GET"]),
    ]
