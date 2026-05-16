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
        def _row(sid: str, display_name: str, project_slug: str, cwd: str, project_dir: str = "", last_modified: float = 0.0) -> dict:
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
            # persistent_sessions. Pro app + webui both group by this.
            # 2026-05-12 — if not explicitly set, derive from display_name
            # pattern so the user's existing project structure surfaces
            # without requiring per-session overlay configuration. Explicit
            # overlays still win; this is a fallback for ungrouped sessions.
            workspace_group = (
                persistent.get("workspace_group") if persistent else None
            ) or _derive_workspace_group(display_name)
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
            # 2026-05-16 -- fields added to bring this endpoint to parity
            # with /api/sessions (the webui-facing list). Webui has used
            # these for months; Pro app couldn't show pinned-first sort,
            # cadence on the row, or the emotive listening state because
            # the data simply wasn't reaching it.
            pinned = (
                bool(persistent.get("pinned", False)) if persistent else False
            )
            cadence = None
            try:
                if state.sessions is not None and live_match is not None:
                    _cfg = state.sessions.config_for(sid)
                    cadence = (_cfg.get("live") or {}).get("cadence")
            except Exception:
                cadence = None
            if not cadence and persistent:
                cadence = ((persistent.get("live_overlay") or {}).get("live") or {}).get("cadence")
            last_user_interaction_at = (
                float(getattr(live_match, "last_user_interaction_at", 0.0))
                if live_match else 0.0
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
                "is_live": (live_match is not None) or (sid in disk_active_sids),
                "enabled": enabled,
                "active_mode": active_mode,
                "last_hook_at": last_hook_at,
                # 2026-05-16 -- expose the catalog's transcript mtime so the
                # phone's "Active" filter can include sessions touched in
                # the last 30 minutes (Claude Code is_live uses a 5-minute
                # window which is too narrow for the user's mental model
                # of "I'm working in this session"). The phone uses this
                # to decide row visibility independent of the strict live
                # badge. Epoch seconds; 0.0 when no transcript known.
                "last_modified": float(last_modified or 0.0),
                "is_companion_active": (sid in active_sids),
                "is_speaking": is_speaking,
                "auto_mode_enabled": auto_mode_enabled,
                "audio_outputs": audio_outputs,
                "audio_misaligned": audio_misaligned,
                "attached_character": _resolve_character(sid),
                # 2026-05-16 -- parity with /api/sessions row.
                "pinned": pinned,
                "cadence": cadence,
                "last_user_interaction_at": last_user_interaction_at,
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

        # 2026-05-12 — drop historical catalog entries whose transcript
        # hasn't been modified in SESSION_VISIBILITY_WINDOW_SEC. Without
        # this, the phone's Sessions list returns every transcript ever
        # indexed (95+ in one observed household, with six entries all
        # named "CodeTalker"). Direct session_id lookups still work via
        # /api/sessions/{sid} for accessing history; only the list view
        # is filtered. Matches the same filter in /api/sessions list.
        import time as _t
        # 2026-05-16 -- bumped from 24h to 30d to match Claude Code's
        # session-list visibility. See same constant in api.py for the
        # rationale; this companion handler must stay in sync so the
        # phone and webui see the same set.
        SESSION_VISIBILITY_WINDOW_SEC = 30 * 24 * 3600
        TRANSCRIPT_LIVE_WINDOW_SEC = 300
        _now = _t.time()
        visible_entries = [
            e for e in catalog.entries()
            if (_now - getattr(e, "last_modified", 0.0)) < SESSION_VISIBILITY_WINDOW_SEC
        ]
        # 2026-05-12 — broader live signal that matches /api/sessions:
        # a session is "live" if it has an in-memory SessionState (hook
        # fired recently) OR its transcript was modified within the live
        # window. The strict in-memory-only check meant the phone showed
        # "Live · 0" right after daemon restart even when active CC
        # sessions were running (no hooks had fired YET against the new
        # daemon process). The catalog-recency check covers that gap.
        disk_active_sids: set[str] = {
            e.session_id for e in visible_entries
            if (_now - getattr(e, "last_modified", 0.0)) < TRANSCRIPT_LIVE_WINDOW_SEC
        }

        rows: list[dict] = []
        seen: set[str] = set()
        for e in visible_entries:
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
                getattr(e, "last_modified", 0.0) or 0.0,
            ))
            seen.add(e.session_id)
        # Sessions that are live but not yet in the catalog (newly spawned).
        for sid, live_match in live_by_sid.items():
            if sid in seen:
                continue
            # Newly spawned (no catalog yet); last_hook_at proxies as
            # last_modified so the phone's recent-activity filter still
            # picks it up immediately.
            _lm = float(getattr(live_match, "last_hook_at", 0.0) or 0.0)
            rows.append(_row(sid, sid[:12], "", live_match.cwd or "", "", _lm))
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
