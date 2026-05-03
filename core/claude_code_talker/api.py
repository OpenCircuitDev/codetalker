"""REST API routes mounted alongside the FastMCP SSE app."""
from __future__ import annotations

import json
import json as _json_lib
import re
import time as _rate_time
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from claude_code_talker.profiles import is_valid_profile_name
from claude_code_talker.persistent_sessions import is_valid_session_id
from claude_code_talker.secrets_store import KNOWN_KEYS as _SECRET_KEYS, SecretsStore as _SecretsStore


CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

_PROJECT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# Module-level rate-limit state, keyed on id(state) so tests with multiple
# state instances don't interfere with each other.
_REFRESH_LAST_AT: dict[int, float] = {}


def _rate_limit_check(state, key: str, min_interval: float) -> bool:
    """Returns True if allowed, False if rate-limited."""
    now = _rate_time.time()
    bucket_key = id(state)
    last = _REFRESH_LAST_AT.get(bucket_key, 0.0)
    if now - last < min_interval:
        return False
    _REFRESH_LAST_AT[bucket_key] = now
    return True

_HOOK_EVENT_NAMES = ["Stop", "Notification", "PreToolUse", "PostToolUse", "UserPromptSubmit"]
_HOOK_ENTRY = {
    "hooks": [
        {"type": "command", "shell": "powershell", "command": "claude-code-talker-hook", "async": True}
    ]
}


def _has_codetalker_hook(entries: list) -> bool:
    for e in entries:
        for h in e.get("hooks", []):
            if h.get("command") == "claude-code-talker-hook":
                return True
    return False


def build_routes(state) -> list[Route]:
    """Build the list of Starlette Route objects bound to this server state."""

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def list_sessions(request: Request) -> JSONResponse:
        live = state.sessions.list_active()
        live_by_sid = {s.session_id: s for s in live}
        merged = []
        if state.catalog is not None:
            catalog_entries = state.catalog.entries()
        else:
            catalog_entries = []
        seen_sids = set()
        for c in catalog_entries:
            sid = c.session_id
            seen_sids.add(sid)
            live_match = live_by_sid.get(sid)
            persistent = state.persistent_sessions.get(sid) if state.persistent_sessions else None
            # Display priority: persistent display_name > Claude Code panel
            # label > catalog auto-title > project_slug
            display_name = (
                (persistent.get("display_name") if persistent else None)
                or (c.vscode_label or None)
                or (c.title or None)
                or c.project_slug
            )
            merged.append({
                "session_id": sid,
                "cwd": (live_match.cwd if live_match else "") or "",
                "project_slug": c.project_slug,
                "title": c.title,
                "display_name": display_name,
                "last_modified": max(
                    c.last_modified,
                    live_match.last_hook_at if live_match else 0.0,
                ),
                "is_live": live_match is not None,
                "enabled": (persistent.get("enabled", True) if persistent else True),
                "attached_profile": (
                    live_match.attached_profile if live_match else (
                        persistent.get("attached_profile") if persistent else None
                    )
                ),
                "has_persistent_settings": persistent is not None,
            })
        # Live sessions not in the catalog (newly created since last scan)
        for sid, live_match in live_by_sid.items():
            if sid in seen_sids:
                continue
            persistent = state.persistent_sessions.get(sid) if state.persistent_sessions else None
            merged.append({
                "session_id": sid,
                "cwd": live_match.cwd or "",
                "project_slug": "",
                "display_name": (persistent.get("display_name") if persistent else None) or sid[:12],
                "last_modified": live_match.last_hook_at,
                "is_live": True,
                "enabled": (persistent.get("enabled", True) if persistent else True),
                "attached_profile": live_match.attached_profile,
                "has_persistent_settings": persistent is not None,
            })
        merged.sort(key=lambda e: e["last_modified"], reverse=True)
        return JSONResponse(merged)

    async def get_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        cfg = state.sessions.config_for(sid)
        return JSONResponse({
            "state": {
                "session_id": s.session_id,
                "cwd": s.cwd,
                "transcript_path": s.transcript_path,
                "last_hook_at": s.last_hook_at,
                "live_overlay": s.live_overlay,
                "attached_profile": s.attached_profile,
            },
            "resolved_cfg": cfg,
        })

    async def put_overlay(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if state.sessions.get(sid) is None:
            return _not_found(f"unknown session: {sid}")
        try:
            partial = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        try:
            state.sessions.update_overlay(sid, partial)
        except KeyError:
            return _not_found(f"unknown session: {sid}")
        cfg = state.sessions.config_for(sid)
        state.sessions.invalidate(sid)  # keep cache cleared after resolving for response
        s = state.sessions.get(sid)
        return JSONResponse({
            "state": {
                "session_id": s.session_id,
                "live_overlay": s.live_overlay,
                "attached_profile": s.attached_profile,
            },
            "resolved_cfg": cfg,
        })

    async def delete_overlay_keypath(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        keypath = request.path_params["keypath"]
        if state.sessions.get(sid) is None:
            return _not_found(f"unknown session: {sid}")
        try:
            state.sessions.remove_overlay_keypath(sid, keypath)
        except KeyError:
            return _not_found(f"unknown session: {sid}")
        cfg = state.sessions.config_for(sid)
        s = state.sessions.get(sid)
        return JSONResponse({
            "state": {"session_id": s.session_id, "live_overlay": s.live_overlay},
            "resolved_cfg": cfg,
        })

    async def attach_profile(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        name = body.get("name", "")
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        if not state.profiles.exists(name):
            return _bad_request(f"profile not found: {name}")
        state.sessions.attach_profile(sid, name)
        if s.cwd:
            state.profiles.set_last_profile_for_cwd(s.cwd, name)
        cfg = state.sessions.config_for(sid)
        return JSONResponse({
            "state": {"session_id": s.session_id, "attached_profile": s.attached_profile},
            "resolved_cfg": cfg,
        })

    async def detach_profile(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        prev_cwd = s.cwd
        state.sessions.detach_profile(sid)
        if prev_cwd:
            state.profiles.clear_last_profile_for_cwd(prev_cwd)
        cfg = state.sessions.config_for(sid)
        return JSONResponse({
            "state": {"session_id": s.session_id, "attached_profile": None},
            "resolved_cfg": cfg,
        })

    async def save_as_profile(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        name = body.get("name", "")
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        path = state.profiles.save(name, dict(s.live_overlay))
        return JSONResponse({"name": name, "path": str(path)})

    async def install_hooks(request: Request) -> JSONResponse:
        path = CLAUDE_SETTINGS_PATH
        if path.exists():
            try:
                data = _json_lib.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
        data.setdefault("hooks", {})
        added = 0
        for ev in _HOOK_EVENT_NAMES:
            entries = data["hooks"].setdefault(ev, [])
            if not _has_codetalker_hook(entries):
                entries.append(dict(_HOOK_ENTRY))
                added += 1
        path.write_text(_json_lib.dumps(data, indent=2), encoding="utf-8")
        return JSONResponse({"installed": True, "hooks_added": added})

    async def mute(request: Request) -> JSONResponse:
        state.cfg["enabled"] = False
        return JSONResponse({"enabled": False})

    async def unmute(request: Request) -> JSONResponse:
        state.cfg["enabled"] = True
        return JSONResponse({"enabled": True})

    async def list_voices(request: Request) -> JSONResponse:
        engine_name = request.query_params.get("engine")
        if not engine_name:
            return _bad_request("query param 'engine' is required")
        engine = state.engines.get(engine_name)
        if engine is None:
            return _bad_request(f"unknown engine: {engine_name}")
        try:
            voices = engine.list_voices()
        except Exception as e:
            return JSONResponse({"error": f"engine list_voices failed: {e}"}, status_code=500)
        return JSONResponse(list(voices))

    async def status(request: Request) -> JSONResponse:
        active_modes = {}
        for s in state.sessions.list_active():
            cfg = state.sessions.config_for(s.session_id)
            active_modes[s.session_id] = cfg.get("active_mode", state.active_mode)
        return JSONResponse({
            "enabled": state.cfg.get("enabled", True),
            "session_count": len(state.sessions.list_active()),
            "active_modes": active_modes,
            "engines": list(state.engines),
            "providers": list(state.providers),
        })

    async def list_profiles(request: Request) -> JSONResponse:
        names = state.profiles.list()
        out = []
        for name in names:
            try:
                content = state.profiles.get(name)
                out.append({"name": name, "key_count": len(content)})
            except Exception:
                out.append({"name": name, "key_count": 0, "corrupted": True})
        return JSONResponse(out)

    async def get_profile(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        try:
            content = state.profiles.get(name)
        except FileNotFoundError:
            return _not_found(f"profile not found: {name}")
        return JSONResponse({"name": name, "content": content})

    async def put_profile(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        state.profiles.save(name, body)
        return JSONResponse({"name": name, "content": body})

    async def delete_profile(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        if not state.profiles.exists(name):
            return _not_found(f"profile not found: {name}")
        # Detach from any sessions that have it attached
        detached = 0
        for s in state.sessions.list_active():
            if s.attached_profile == name:
                state.sessions.detach_profile(s.session_id)
                detached += 1
        state.profiles.delete(name)
        return JSONResponse({"deleted": True, "detached_from_sessions": detached})

    async def list_catalog(request: Request) -> JSONResponse:
        project = request.query_params.get("project")
        if project is not None and not _PROJECT_RE.match(project):
            return _bad_request(f"invalid project: {project!r}")
        if state.catalog is None:
            return JSONResponse([])
        if project:
            entries = state.catalog.entries_for_project(project)
        else:
            entries = state.catalog.entries()
        out = [
            {
                "session_id": e.session_id,
                "project_slug": e.project_slug,
                "transcript_path": str(e.transcript_path),
                "last_modified": e.last_modified,
                "title": e.title,
                "vscode_label": e.vscode_label,
            }
            for e in entries
        ]
        return JSONResponse(out)

    async def refresh_catalog(request: Request) -> JSONResponse:
        if not _rate_limit_check(state, "catalog_refresh", 5.0):
            return JSONResponse({"error": "rate limited (1 refresh per 5s)"}, status_code=429)
        if state.catalog is None:
            return JSONResponse({"scanned": 0})
        scanned = state.catalog.refresh()
        return JSONResponse({"scanned": scanned})

    async def get_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        payload = state.persistent_sessions.get(sid)
        if payload is None:
            return _not_found(f"no persistent settings for session: {sid}")
        return JSONResponse(payload)

    async def put_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        live_overlay = body.get("live_overlay")
        if live_overlay is not None and not isinstance(live_overlay, dict):
            return _bad_request("live_overlay must be a JSON object")
        enabled = body.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            return _bad_request("enabled must be a boolean")
        # Build canonical payload — preserve any unknown keys for schema-drift forward-compat
        payload = dict(body)
        payload.setdefault("live_overlay", {})
        payload.setdefault("enabled", True)
        payload.setdefault("attached_profile", None)
        payload.setdefault("display_name", None)
        payload["last_modified"] = _rate_time.time()
        state.persistent_sessions.save(sid, payload)
        return JSONResponse({"saved": True, "session_id": sid})

    async def delete_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        existed = state.persistent_sessions.exists(sid)
        state.persistent_sessions.delete(sid)
        return JSONResponse({"deleted": existed})

    async def get_secrets(request: Request) -> JSONResponse:
        """Return all known API keys, redacted (last 4 chars). Source-of-truth
        per key (env vs file) is included so the user knows where it's coming
        from."""
        if state.secrets is None:
            return JSONResponse({})
        on_disk = state.secrets.load()
        out: dict[str, dict] = {}
        import os as _os
        for env_name, file_key in [
            ("ANTHROPIC_API_KEY", "anthropic_api_key"),
            ("OPENAI_API_KEY", "openai_api_key"),
            ("OPENROUTER_API_KEY", "openrouter_api_key"),
            ("ELEVENLABS_API_KEY", "elevenlabs_api_key"),
        ]:
            env_val = _os.environ.get(env_name)
            if env_val:
                out[file_key] = {"set": True, "redacted": _SecretsStore.redact(env_val), "source": "env"}
            elif file_key in on_disk:
                out[file_key] = {"set": True, "redacted": _SecretsStore.redact(on_disk[file_key]), "source": "file"}
            else:
                out[file_key] = {"set": False, "redacted": None, "source": None}
        return JSONResponse(out)

    async def put_secrets(request: Request) -> JSONResponse:
        """Update one or more API keys. Empty-string deletes a key. Body shape:
        {"openai_api_key": "sk-...", "anthropic_api_key": ""}"""
        if state.secrets is None:
            return _bad_request("secrets store not configured")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        partial: dict[str, str] = {}
        for k, v in body.items():
            if k not in _SECRET_KEYS:
                return _bad_request(f"unknown secret key: {k!r}")
            if not isinstance(v, str):
                return _bad_request(f"value for {k} must be a string")
            partial[k] = v
        state.secrets.update(partial)
        return JSONResponse({"saved": True, "note": "Restart daemon for changes to take effect"})

    # Curated cost-effective default model lists per provider. Used for the UI
    # dropdown when the provider doesn't expose a /models endpoint or when an
    # offline / cached list is sufficient.
    _CURATED_MODELS: dict[str, list[dict]] = {
        "ollama": [
            {"id": "llama3.2", "label": "llama3.2 (3B, default)", "tier": "local"},
            {"id": "qwen2.5:3b", "label": "qwen2.5:3b", "tier": "local"},
            {"id": "phi3.5", "label": "phi3.5", "tier": "local"},
        ],
        "anthropic": [
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 (fast/cheap)", "tier": "cheap"},
            {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (balanced)", "tier": "mid"},
            {"id": "claude-opus-4-7", "label": "Claude Opus 4.7 (premium)", "tier": "premium"},
        ],
        "openai": [
            {"id": "gpt-4o-mini", "label": "GPT-4o mini (cheap default)", "tier": "cheap"},
            {"id": "gpt-5-mini", "label": "GPT-5 mini", "tier": "cheap"},
            {"id": "gpt-4o", "label": "GPT-4o", "tier": "mid"},
            {"id": "gpt-5", "label": "GPT-5 (premium)", "tier": "premium"},
        ],
        "openrouter": [
            {"id": "google/gemini-2.0-flash-001", "label": "Gemini 2.0 Flash (cheapest, default)", "tier": "cheap"},
            {"id": "openai/gpt-4o-mini", "label": "GPT-4o mini via OpenRouter", "tier": "cheap"},
            {"id": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 via OpenRouter", "tier": "cheap"},
            {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B (cheap+capable)", "tier": "cheap"},
            {"id": "anthropic/claude-sonnet-4-6", "label": "Claude Sonnet 4.6 via OpenRouter", "tier": "mid"},
        ],
    }

    # Cache OpenRouter's live /models response so the dropdown doesn't refetch
    # every page load.
    _openrouter_models_cache: dict = {"data": None, "fetched_at": 0.0}

    async def list_llm_models(request: Request) -> JSONResponse:
        """Return curated + (optionally cached) model list per provider.

        Response shape: {provider: {default: <model_id>, models: [...]}}
        """
        out: dict[str, dict] = {}
        # Pull configured-default model from cfg per provider so the UI shows
        # the right "current" item.
        cfg_providers = (state.cfg.get("providers") or {})
        for provider, models in _CURATED_MODELS.items():
            cfg_model = (cfg_providers.get(provider) or {}).get("model")
            if provider == "openrouter":
                default = cfg_model or "google/gemini-2.0-flash-001"
                live = _openrouter_models_cache["data"]
                merged = list(models)
                if live:
                    seen = {m["id"] for m in merged}
                    for m in live:
                        if m["id"] not in seen:
                            merged.append(m)
            elif provider == "openai":
                default = cfg_model or "gpt-4o-mini"
                merged = list(models)
            elif provider == "anthropic":
                default = cfg_model or "claude-haiku-4-5-20251001"
                merged = list(models)
            else:  # ollama
                default = cfg_model or "llama3.2"
                merged = list(models)
            available = provider in (state.providers or {})
            out[provider] = {
                "default": default,
                "models": merged,
                "available": available,
            }
        return JSONResponse(out)

    async def get_narration_log(request: Request) -> JSONResponse:
        """Phase 11: return the last N narrated lines, optionally filtered by session."""
        if state.narration_log is None:
            return JSONResponse([])
        try:
            limit = int(request.query_params.get("limit", 100))
        except ValueError:
            return _bad_request("limit must be an integer")
        limit = max(1, min(1000, limit))
        sid = request.query_params.get("session_id")
        if sid:
            if not is_valid_session_id(sid):
                return _bad_request(f"invalid session_id: {sid!r}")
            entries = state.narration_log.find_for_session(sid, limit=limit)
        else:
            entries = state.narration_log.tail(n=limit)
        return JSONResponse(entries)

    async def get_usage(request: Request) -> JSONResponse:
        """Phase 12: return token + cost rollup, optionally since a unix timestamp."""
        if state.token_tracker is None:
            return JSONResponse({})
        since_str = request.query_params.get("since")
        since = None
        if since_str:
            try:
                since = float(since_str)
            except ValueError:
                return _bad_request("since must be a unix timestamp")
        return JSONResponse(state.token_tracker.rollup(since=since))

    async def get_tts_cache_stats(request: Request) -> JSONResponse:
        """Phase 10: TTS cache stats (entries, bytes, hit ratio)."""
        if state.tts_cache is None:
            return JSONResponse({})
        return JSONResponse(state.tts_cache.stats())

    async def clear_tts_cache(request: Request) -> JSONResponse:
        """Phase 10: clear the TTS cache (returns count of files removed)."""
        if state.tts_cache is None:
            return JSONResponse({"deleted": 0})
        deleted = state.tts_cache.clear()
        return JSONResponse({"deleted": deleted})

    async def reload_config(request: Request) -> JSONResponse:
        """Phase 12: hot-reload state.cfg from disk without restarting the daemon.

        Re-runs load_full_config() and replaces state.cfg in place. Cached per-
        session resolved configs are invalidated so the new values flow on the
        next narration tick.
        """
        if not _rate_limit_check(state, "config_reload", 2.0):
            return JSONResponse({"error": "rate limited"}, status_code=429)
        from claude_code_talker.config import load_full_config
        try:
            new_cfg = load_full_config()
        except Exception as e:
            return JSONResponse({"error": f"reload failed: {e}"}, status_code=500)
        # Mutate in place so all callers holding a ref to state.cfg see the new values.
        state.cfg.clear()
        state.cfg.update(new_cfg)
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        return JSONResponse({"reloaded": True, "key_count": len(state.cfg)})

    async def bulk_session_op(request: Request) -> JSONResponse:
        """Phase 11: bulk operations on sessions matching a filter.

        Body: {"action": "disable"|"enable", "filter": {"project_slug": str}}
        Writes to PersistentSessionStore so changes survive restart.
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        action = body.get("action")
        if action not in ("disable", "enable"):
            return _bad_request("action must be 'disable' or 'enable'")
        flt = body.get("filter") or {}
        if not isinstance(flt, dict):
            return _bad_request("filter must be a JSON object")
        project_slug = flt.get("project_slug")
        if not project_slug or not isinstance(project_slug, str):
            return _bad_request("filter.project_slug is required")
        if state.catalog is None or state.persistent_sessions is None:
            return _bad_request("catalog or persistent store unavailable")
        targets = state.catalog.entries_for_project(project_slug)
        new_enabled = (action == "enable")
        modified = 0
        import time as _t
        for entry in targets:
            sid = entry.session_id
            current = state.persistent_sessions.get(sid) or {
                "live_overlay": {}, "attached_profile": None, "enabled": True,
                "display_name": None, "last_modified": 0.0,
            }
            if current.get("enabled") != new_enabled:
                current["enabled"] = new_enabled
                current["last_modified"] = _t.time()
                state.persistent_sessions.save(sid, current)
                # If the session is currently live, also flip the in-memory state.
                live = state.sessions.get(sid)
                if live is not None:
                    live.enabled = new_enabled
                modified += 1
        return JSONResponse({
            "action": action, "project_slug": project_slug,
            "matched": len(targets), "modified": modified,
        })

    async def chat_with_session(request: Request) -> JSONResponse:
        """Phase 9: ask the LLM a question about a session.

        Body: {"question": str, "narrate": bool (optional), "max_tokens": int (optional)}
        Picks the provider/model from cfg.modes.live (same as live narration).
        Honors teacher_mode (global + per-session overlay).
        """
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        question = (body.get("question") or "").strip()
        if not question:
            return _bad_request("question must be a non-empty string")
        narrate = bool(body.get("narrate", False))
        max_tokens = int(body.get("max_tokens", 400))

        from claude_code_talker.chat_panel import gather_session_context, answer_question
        from pathlib import Path as _P
        s = state.sessions.get(sid)
        # Pull resolved cfg so per-session teacher_mode wins
        try:
            cfg = state.sessions.config_for(sid)
        except Exception:
            cfg = state.cfg
        teacher_cfg = cfg.get("teacher_mode")
        # Pick provider — same logic as live mode
        from claude_code_talker.server import _select_provider
        provider = _select_provider(state, "live")
        if provider is None:
            return JSONResponse({"error": "no LLM provider available"}, status_code=503)
        # Gather context
        transcript_path = None
        events = []
        if s is not None and s.transcript_path:
            transcript_path = _P(s.transcript_path)
        elif state.catalog is not None:
            entry = state.catalog.entry_for(sid)
            if entry is not None:
                transcript_path = entry.transcript_path
        if state.event_buffer is not None:
            events = state.event_buffer.recent(40)
        ctx = gather_session_context(
            transcript_path=transcript_path, events=events,
        )
        answer = await answer_question(
            question=question, context=ctx, provider=provider,
            teacher_cfg=teacher_cfg, max_tokens=max_tokens,
        )
        result = {"answer": answer, "session_id": sid}
        # Optionally narrate the response
        if narrate and answer and not answer.startswith("(provider error"):
            from claude_code_talker.audio import AudioJob
            voice_cfg = cfg.get("voice") or {}
            engine_name = voice_cfg.get("engine", "piper")
            engine = state.engines.get(engine_name)
            voice = voice_cfg.get("model")
            if engine is not None and voice:
                state.audio_queue.submit(AudioJob(
                    text=answer,
                    voice=voice,
                    rate=float(voice_cfg.get("rate", 1.0)),
                    engine_name=engine_name,
                    audio_format=getattr(engine, "audio_format", "wav"),
                ))
                result["narrated"] = True
        return JSONResponse(result)

    async def get_teacher(request: Request) -> JSONResponse:
        """Return the global teacher_mode cfg block (with defaults filled in)."""
        from claude_code_talker.teacher_mode import DEFAULT_TEACHER_CONFIG
        current = state.cfg.get("teacher_mode") or {}
        merged = {**DEFAULT_TEACHER_CONFIG, **current}
        return JSONResponse(merged)

    async def put_teacher(request: Request) -> JSONResponse:
        """Update the global teacher_mode cfg block. Per-session overrides set
        via the existing /api/sessions/<sid>/overlay endpoint with key
        'teacher_mode'.

        Accepts: enabled, depth_level (1-5), substitution, glossary, reframe,
        verbosity (concise|standard|expanded), granularity (combined|per-file).
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        for key in ("enabled", "substitution", "glossary", "reframe"):
            if key in body and not isinstance(body[key], bool):
                return _bad_request(f"{key} must be a boolean")
        if "depth_level" in body:
            try:
                depth = int(body["depth_level"])
            except (TypeError, ValueError):
                return _bad_request("depth_level must be an integer 1-5")
            if not 1 <= depth <= 5:
                return _bad_request("depth_level must be 1-5")
            body["depth_level"] = depth
        if "verbosity" in body and body["verbosity"] not in ("concise", "standard", "expanded"):
            return _bad_request("verbosity must be concise/standard/expanded")
        if "granularity" in body and body["granularity"] not in ("combined", "per-file"):
            return _bad_request("granularity must be combined/per-file")
        current = state.cfg.get("teacher_mode") or {}
        current.update({k: v for k, v in body.items()
                       if k in ("enabled", "depth_level", "substitution",
                                "glossary", "reframe", "verbosity", "granularity")})
        state.cfg["teacher_mode"] = current
        # Persist to overlay so it survives daemon restart.
        try:
            import yaml as _yaml
            from pathlib import Path as _P
            p = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
            p.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if p.exists():
                try:
                    existing = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                except Exception:
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing["teacher_mode"] = current
            p.write_text(_yaml.safe_dump(existing, sort_keys=True), encoding="utf-8")
        except Exception:
            pass
        # Invalidate per-session cached cfgs so the new teacher block flows.
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        return JSONResponse(current)

    async def put_llm_default(request: Request) -> JSONResponse:
        """Set the default LLM provider + model for narration AND chat.

        Body: {"provider": "openrouter", "model": "google/gemini-2.0-flash-001"}

        Optional field: "mode" — if provided, only update that specific mode's
        provider+model (one of "live", "brief", "chat", "prompt-brief").
        If omitted, updates ALL of live/brief (existing behavior).

        Updates:
          - state.cfg.providers.<provider>.model — model chosen for that provider
          - state.cfg.modes.<mode>.{provider, model} — per-mode overrides
          - the live provider instance's model attribute (immediate effect, all-modes only)
          - per-session resolved cfg caches are invalidated

        Daemon restart reverts to whatever's in cfg on disk; for permanent
        changes also edit ~/.claude/scripts/tts_config.yaml or call
        /api/config/reload after editing.
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        provider = body.get("provider")
        model = body.get("model")
        mode_scope = body.get("mode")  # optional — None = all modes
        if not provider or not isinstance(provider, str):
            return _bad_request("provider is required")
        if not model or not isinstance(model, str):
            return _bad_request("model is required")
        if provider not in (state.providers or {}):
            return _bad_request(f"provider '{provider}' not registered (check API key, then restart daemon)")
        if mode_scope is not None and not isinstance(mode_scope, str):
            return _bad_request("mode must be a string or omitted")
        cfg_providers = state.cfg.setdefault("providers", {})
        cfg_providers.setdefault(provider, {})["model"] = model
        cfg_modes = state.cfg.setdefault("modes", {})

        if mode_scope:
            # Per-mode: only update that mode's provider and model
            cfg_modes.setdefault(mode_scope, {})["provider"] = provider
            cfg_modes.setdefault(mode_scope, {})["model"] = model
            updated_modes = [mode_scope]
        else:
            # All-modes (existing behavior): update live + brief
            # CRITICAL: also flip which provider live/brief modes use, otherwise
            # _select_provider keeps falling back to ollama and live narration
            # silently 404s when the user expected OpenRouter / OpenAI / Anthropic.
            cfg_modes.setdefault("live", {})["provider"] = provider
            cfg_modes.setdefault("brief", {})["provider"] = provider
            updated_modes = ["live", "brief"]
            # Update live provider instance's model attribute so the change takes
            # effect immediately for in-flight calls.
            prov_obj = (state.providers or {}).get(provider)
            if prov_obj is not None and hasattr(prov_obj, "model"):
                prov_obj.model = model

        # Re-bind LiveMode + BriefMode to the new provider instance so future
        # narrations use it (don't keep using the old ollama instance).
        if hasattr(state, "modes") and state.modes:
            from claude_code_talker.server import _select_provider
            new_prov = _select_provider(state, "live")
            if state.modes.get("live") is not None:
                state.modes["live"].provider = new_prov
            new_prov_brief = _select_provider(state, "brief")
            if state.modes.get("brief") is not None:
                state.modes["brief"].provider = new_prov_brief
        # Invalidate per-session caches so resolved cfg picks up the new values.
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        # Persist to disk so the change survives daemon restart.
        _persist_default_provider(provider, model, mode=mode_scope)
        result: dict = {
            "saved": True, "provider": provider, "model": model,
            "updated_modes": updated_modes,
            "persisted": True,
        }
        if not mode_scope:
            result["live_uses"] = provider
            result["brief_uses"] = provider
        return JSONResponse(result)

    async def refresh_openrouter_models(request: Request) -> JSONResponse:
        """Fetch fresh model list from OpenRouter's public /models endpoint.

        Cached for the daemon's lifetime once fetched (call again to refresh).
        Doesn't require an API key — the OpenRouter /models endpoint is public.
        """
        if not _rate_limit_check(state, "openrouter_refresh", 30.0):
            return JSONResponse({"error": "rate limited (1 refresh per 30s)"}, status_code=429)
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get("https://openrouter.ai/api/v1/models")
                r.raise_for_status()
                payload = r.json()
        except (httpx.HTTPError, ValueError) as e:
            return JSONResponse({"error": f"openrouter fetch failed: {e}"}, status_code=502)
        data = payload.get("data") or []
        models = []
        for m in data:
            mid = m.get("id")
            if not isinstance(mid, str):
                continue
            pricing = m.get("pricing") or {}
            try:
                prompt_price = float(pricing.get("prompt", 0))
                comp_price = float(pricing.get("completion", 0))
            except (TypeError, ValueError):
                prompt_price = comp_price = 0.0
            # Tier classification: 'cheap' if both <= $1/M tokens, else 'mid'/'premium'.
            per_million_in = prompt_price * 1_000_000
            per_million_out = comp_price * 1_000_000
            if per_million_in <= 1.0 and per_million_out <= 5.0:
                tier = "cheap"
            elif per_million_in <= 5.0 and per_million_out <= 15.0:
                tier = "mid"
            else:
                tier = "premium"
            models.append({
                "id": mid,
                "label": f"{mid} (${per_million_in:.2f}/$ {per_million_out:.2f}/M)",
                "tier": tier,
                "prompt_per_million": per_million_in,
                "completion_per_million": per_million_out,
            })
        # Sort cheap first
        tier_order = {"cheap": 0, "mid": 1, "premium": 2}
        models.sort(key=lambda m: (tier_order.get(m["tier"], 3), m["prompt_per_million"]))
        _openrouter_models_cache["data"] = models
        import time as _t
        _openrouter_models_cache["fetched_at"] = _t.time()
        return JSONResponse({"refreshed": True, "model_count": len(models)})

    return [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/catalog", list_catalog, methods=["GET"]),
        Route("/api/catalog/refresh", refresh_catalog, methods=["POST"]),
        Route("/api/persistent-sessions/{session_id}", get_persistent_session, methods=["GET"]),
        Route("/api/persistent-sessions/{session_id}", put_persistent_session, methods=["PUT"]),
        Route("/api/persistent-sessions/{session_id}", delete_persistent_session, methods=["DELETE"]),
        Route("/api/secrets", get_secrets, methods=["GET"]),
        Route("/api/secrets", put_secrets, methods=["PUT"]),
        Route("/api/llm-models", list_llm_models, methods=["GET"]),
        Route("/api/llm-models/default", put_llm_default, methods=["PUT"]),
        Route("/api/llm-models/openrouter/refresh", refresh_openrouter_models, methods=["POST"]),
        Route("/api/teacher", get_teacher, methods=["GET"]),
        Route("/api/teacher", put_teacher, methods=["PUT"]),
        Route("/api/sessions/{session_id}/chat", chat_with_session, methods=["POST"]),
        Route("/api/narration-log", get_narration_log, methods=["GET"]),
        Route("/api/usage", get_usage, methods=["GET"]),
        Route("/api/tts-cache", get_tts_cache_stats, methods=["GET"]),
        Route("/api/tts-cache", clear_tts_cache, methods=["DELETE"]),
        Route("/api/config/reload", reload_config, methods=["POST"]),
        Route("/api/sessions/bulk", bulk_session_op, methods=["POST"]),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions/{session_id}", get_session, methods=["GET"]),
        Route("/api/sessions/{session_id}/overlay", put_overlay, methods=["PUT"]),
        Route("/api/sessions/{session_id}/overlay/{keypath:path}", delete_overlay_keypath, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/attach-profile", attach_profile, methods=["POST"]),
        Route("/api/sessions/{session_id}/profile", detach_profile, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/save-as-profile", save_as_profile, methods=["POST"]),
        Route("/api/profiles", list_profiles, methods=["GET"]),
        Route("/api/profiles/{name}", get_profile, methods=["GET"]),
        Route("/api/profiles/{name}", put_profile, methods=["PUT"]),
        Route("/api/profiles/{name}", delete_profile, methods=["DELETE"]),
        Route("/api/voices", list_voices, methods=["GET"]),
        Route("/api/status", status, methods=["GET"]),
        Route("/api/mute", mute, methods=["POST"]),
        Route("/api/unmute", unmute, methods=["POST"]),
        Route("/api/install-hooks", install_hooks, methods=["POST"]),
    ]


def _persist_default_provider(provider: str, model: str, *, mode: str | None = None) -> None:
    """Write the user's chosen LLM default to a small overlay YAML at
    ~/.claude/scripts/codetalker/cfg-overlay.yaml so it survives restarts.

    The daemon's config loader merges this overlay on top of the base cfg.
    Best-effort: any I/O failure is silenced (the in-memory PUT still works).

    Args:
        provider: Provider name (e.g. "openrouter").
        model: Model ID (e.g. "google/gemini-2.0-flash-001").
        mode: If provided, only update that mode's {provider, model} entry.
              If None (default), update live + brief (existing all-modes behavior).
    """
    try:
        import yaml as _yaml
        from pathlib import Path as _P
        p = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if p.exists():
            try:
                existing = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                existing = {}
        if not isinstance(existing, dict):
            existing = {}
        existing.setdefault("providers", {}).setdefault(provider, {})["model"] = model
        if mode:
            # Per-mode: write provider + model into that specific mode block
            existing.setdefault("modes", {}).setdefault(mode, {})["provider"] = provider
            existing.setdefault("modes", {}).setdefault(mode, {})["model"] = model
        else:
            # All-modes: update live + brief (existing behavior)
            existing.setdefault("modes", {}).setdefault("live", {})["provider"] = provider
            existing.setdefault("modes", {}).setdefault("brief", {})["provider"] = provider
        p.write_text(_yaml.safe_dump(existing, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=400)


def _not_found(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=404)


async def _read_json(request: Request) -> dict:
    """Parse JSON body or raise ValueError."""
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data
