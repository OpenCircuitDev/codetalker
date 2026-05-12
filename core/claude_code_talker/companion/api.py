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
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        catalog = state.catalog
        if catalog is None:
            return JSONResponse([])

        # CCT-31 + CCT-28: resolve attached_character → full character record so
        # the AR companion knows whose voice + persona + mesh is bound to each
        # session. Voice cloning lands here naturally — when a character has a
        # cloned voice_ref, the daemon's TTS pipeline already routes audio
        # through that voice; the companion just needs to display "who's
        # speaking" so the listener gets the visual + audio match.
        live_by_sid: dict[str, object] = {}
        try:
            for s in (state.sessions.list_active() if state.sessions else []):
                live_by_sid[s.session_id] = s
        except AttributeError:
            pass
        characters = state.characters
        # 2026-05-11 — was `active_sid` (single). Now read the full set so
        # `is_companion_active` reflects multi-active membership. Old single
        # field still populated for legacy callers (audio.py + buddy).
        active_sids = getattr(state, "companion_active_sessions", None) or set()
        if not active_sids:
            legacy = getattr(state, "companion_active_session", None)
            if legacy:
                active_sids = {legacy}

        def _resolve_character(sid: str) -> dict | None:
            live = live_by_sid.get(sid)
            cid = getattr(live, "attached_character", None) if live else None
            if not cid and state.persistent_sessions is not None:
                persistent = state.persistent_sessions.get(sid)
                if persistent:
                    cid = persistent.get("attached_character")
            if not cid or characters is None:
                return None
            char = characters.get(cid)
            if char is None:
                return None
            return {
                "id": char.id,
                "display_name": char.display_name,
                "persona": getattr(char, "persona", None),
                "voice_ref": char.voice_ref,
                "mesh_path": getattr(char, "mesh_path", None),
            }

        # CCT-32 v0.1.0 polish — extra fields the Pro Sessions list redesign needs:
        # project_slug (grouping), enabled (mute indicator + inline toggle),
        # active_mode (brief/live quick pick), last_hook_at (speaking pulse proxy),
        # is_companion_active (which row to badge "ACTIVE" on the phone),
        # cwd (so the companion can mirror Claude Code's per-cwd grouping —
        # codetalker's project_slug collapses distinct workspaces under shared
        # parent directory names).
        def _row(sid: str, display_name: str, project_slug: str, cwd: str, project_dir: str = "") -> dict:
            live_match = live_by_sid.get(sid)
            persistent = (
                state.persistent_sessions.get(sid)
                if state.persistent_sessions is not None
                else None
            )
            enabled = (
                persistent.get("enabled", True) if persistent else True
            )
            # Pull active_mode from the resolved config when sessions store is
            # available; fallback to the persistent overlay or daemon default.
            active_mode = None
            try:
                if state.sessions is not None and live_match is not None:
                    cfg = state.sessions.config_for(sid)
                    active_mode = cfg.get("active_mode")
            except Exception:
                active_mode = None
            if not active_mode and persistent:
                active_mode = (persistent.get("live_overlay") or {}).get("active_mode")
            if not active_mode:
                active_mode = getattr(state, "active_mode", None) or "live"
            last_hook_at = (
                getattr(live_match, "last_hook_at", 0.0) if live_match else 0.0
            )
            # Prefer the live session's cwd (always current); fall back to the
            # catalog's recorded cwd when the session isn't currently running.
            row_cwd = (
                (live_match.cwd if live_match else None)
                or cwd
                or ""
            )
            # v0.1.0 polish — user-defined workspace group, persisted in
            # persistent_sessions. Pro app + webui both group by this; null
            # means "Ungrouped" so the Pro app shows it under that bucket.
            workspace_group = (
                persistent.get("workspace_group") if persistent else None
            )
            # v0.1.0 unification — speaking state, auto-mode toggle, and
            # per-session audio routing for the unified UI.
            is_speaking = (
                bool(getattr(live_match, "is_speaking", False))
                if live_match else False
            )
            auto_mode_enabled = (
                bool(persistent.get("auto_mode_enabled", False))
                if persistent else False
            )
            audio_outputs = (
                persistent.get("audio_outputs") if persistent else None
            )
            # 2026-05-11 Tier-A.2 — companion-side mirror of the
            # audio_misaligned flag used by /api/sessions. True iff this
            # session has a companion sink configured (phone/glasses) but
            # no live audio_hub subscriber. The Android app uses this to
            # render a "configured but not receiving" badge AND to
            # auto-subscribe on next poll (Tier-B).
            audio_misaligned = False
            try:
                if audio_outputs and isinstance(audio_outputs, (list, tuple)):
                    outs_lower = {str(o).lower() for o in audio_outputs}
                    if outs_lower & {"phone", "glasses"}:
                        hub = getattr(state, "audio_hub", None)
                        subs = (
                            getattr(hub, "_subscribers", {}).get(sid, [])
                            if hub is not None else []
                        )
                        audio_misaligned = not subs
            except Exception:
                audio_misaligned = False
            return {
                "session_id": sid,
                "display_name": display_name,
                "project_slug": project_slug,
                "cwd": row_cwd,
                # v0.1.0 polish — Claude Code's project directory name
                # (e.g. "C--Users-brand-Documents-Unreal-Projects-BlueprintForge-Workbench").
                # This survives session eviction (catalog stores transcript_path
                # whose parent IS this dir), so the Pro Sessions list can group
                # dormant + live sessions consistently by workspace.
                "project_dir": project_dir,
                "workspace_group": workspace_group,
                "is_live": live_match is not None,
                "enabled": enabled,
                "active_mode": active_mode,
                "last_hook_at": last_hook_at,
                "is_companion_active": (sid in active_sids),
                "is_speaking": is_speaking,
                "auto_mode_enabled": auto_mode_enabled,
                "audio_outputs": audio_outputs,
                "audio_misaligned": audio_misaligned,
                "attached_character": _resolve_character(sid),
            }

        # v0.1.0 polish — align display_name precedence with the broader
        # /api/sessions endpoint so user `/title` renames (which land in
        # persistent.display_name) take priority, and slug-derived names are
        # used before the cached auto-title. Mirroring the chain documented
        # in api.py's list_sessions handler:
        #   persistent display_name (codetalker-set / user rename)
        #   > Claude Code custom_title (verbatim)
        #   > vscode panel label
        #   > slug-derived display name
        #   > catalog auto-title (cached first prompt)
        #   > project_slug fallback
        from claude_code_talker.catalog import _slug_to_display_name

        def _resolve_display_name(e) -> str:
            persistent = (
                state.persistent_sessions.get(e.session_id)
                if state.persistent_sessions is not None
                else None
            )
            slug_display = _slug_to_display_name(e.slug) if e.slug else ""
            return (
                (persistent.get("display_name") if persistent else None)
                or (e.custom_title or None)
                or (e.vscode_label or None)
                or (slug_display or None)
                or (e.title or None)
                or e.project_slug
            )

        rows: list[dict] = []
        seen: set[str] = set()
        for e in catalog.entries():
            # The catalog Entry doesn't store cwd directly, but transcript_path
            # lives at `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl` so
            # `transcript_path.parent.name` is the canonical Claude Code project
            # directory — the right grouping key for the Sessions list.
            project_dir = ""
            try:
                p = getattr(e, "transcript_path", None)
                if p is not None:
                    project_dir = p.parent.name
            except Exception:
                project_dir = ""
            rows.append(_row(
                e.session_id,
                _resolve_display_name(e),
                e.project_slug,
                getattr(e, "cwd", "") or "",
                project_dir,
            ))
            seen.add(e.session_id)
        # Sessions that are live but not yet in the catalog (newly spawned).
        for sid, live_match in live_by_sid.items():
            if sid in seen:
                continue
            rows.append(_row(sid, sid[:12], "", live_match.cwd or "", ""))
        return JSONResponse(rows)

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
        active_sid = getattr(state, "companion_active_session", None) or bid

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
                    if state.sessions is not None and active_sid:
                        try:
                            cfg = state.sessions.config_for(active_sid)
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
                            session_id=active_sid or "",
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

    return [
        Route("/api/companion/pair", pair, methods=["POST"]),
        Route("/api/companion/sessions", list_sessions, methods=["GET"]),
        Route("/api/companion/start-buddy", start_buddy, methods=["POST"]),
        Route("/api/companion/inject", inject, methods=["POST"]),
        Route("/api/companion/active-session", active_session, methods=["POST"]),
        Route("/api/companion/active-sessions", active_sessions_list, methods=["GET"]),
        Route("/api/companion/audio-stream/{session_id}", audio_stream, methods=["GET"]),
        Route("/api/companion/screen-frame/{kind}", screen_frame, methods=["GET"]),
    ]
