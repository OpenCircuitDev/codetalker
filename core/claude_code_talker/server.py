"""MCP server entry point + tool registry.

This is the single long-running process. Hooks and extensions both talk to it.
Phase 1 wires Stop and Notification handlers; Phase 2 adds PreToolUse and
PostToolUse for live narration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from claude_code_talker.audio import AudioJob, AudioQueue
from claude_code_talker.cadence import make_cadence
from claude_code_talker.config import load_full_config
from claude_code_talker.engines import PiperEngine
from claude_code_talker.event_buffer import Event, EventBuffer, score_significance
from claude_code_talker.modes.base import ModeStrategy
from claude_code_talker.modes.direct import DirectMode
from claude_code_talker.modes.brief import BriefMode
from claude_code_talker.modes.live import LiveMode
from claude_code_talker.profiles import ProfileStore
from claude_code_talker.providers import OllamaProvider
from claude_code_talker.catalog import SessionCatalog
from claude_code_talker.persistent_sessions import PersistentSessionStore
from claude_code_talker.secrets_store import SecretsStore
from claude_code_talker.sessions import SessionRegistry
from claude_code_talker.narration_log import NarrationLog
from claude_code_talker.token_tracker import TokenTracker
from claude_code_talker.tts_cache import TTSCache
from claude_code_talker.virtual_eval.history import TuningHistory
from claude_code_talker.session_focus import SessionFocusRegistry
from claude_code_talker.transcript_watcher import TranscriptWatcher


PIPER_DIR = Path.home() / ".claude" / "scripts" / "piper" / "piper"
VOICES_DIR = Path.home() / ".claude" / "scripts" / "piper" / "voices"


@dataclass
class ServerState:
    cfg: dict
    engines: dict[str, object]
    providers: dict[str, object]
    modes: dict[str, ModeStrategy]
    active_mode: str = "direct"
    audio_queue: AudioQueue = None  # set in build_server_state
    shutting_down: bool = False
    uvicorn_server: object = None  # set in serve_foreground so tts_shutdown can signal it
    event_buffer: EventBuffer = None  # NEW: rolling event buffer for Mode C live narration
    sessions: SessionRegistry = None
    profiles: ProfileStore = None
    catalog: SessionCatalog = None
    persistent_sessions: PersistentSessionStore = None
    secrets: SecretsStore = None
    narration_log: NarrationLog = None
    token_tracker: TokenTracker = None
    tts_cache: TTSCache = None
    tuning_history: TuningHistory = None
    virtual_eval_latest: object = None
    session_focus: SessionFocusRegistry = None
    # Phase 14 v0.4.0 — voice install task tracking + preview audio tokens
    voice_install_tasks: dict = None   # str → InstallTaskState
    voice_preview_audio: dict = None   # token str → Path
    # Phase 23 — fan-out narration event stream consumed by /api/narration-stream
    narration_stream: object = None
    # Phase 13.9c Task 7 — continuous transcript watcher (pre-populates prose cache)
    transcript_watcher: TranscriptWatcher = None
    # Phase 25a — Character store (file-backed CRUD on ~/.claude/scripts/codetalker/characters/)
    characters: object = None
    # Phase 25c — voice clone job tracker (sidecar JSON per job)
    clone_jobs: object = None
    # Phase 25b — mesh job tracker (sidecar JSON per job at <home>/models/_jobs)
    mesh_jobs: object = None
    # Phase 25b — root for downloaded mesh files (<home>/models/<character_id>/<job_id>.<ext>)
    mesh_models_root: object = None


def _select_provider(state: "ServerState", mode_name: str) -> "object | None":
    """Pick the LLM provider for a mode based on cfg.modes.<name>.provider.

    If cfg.modes.<mode_name>.model is also set AND differs from the registered
    provider's current model, a cloned provider instance is returned with the
    override model.  The registered instance in state.providers is never mutated.

    Falls back to ollama if the preference isn't registered, or to any
    available provider if ollama is also missing.
    """
    mode_cfg = ((state.cfg.get("modes") or {}).get(mode_name) or {})
    pref = mode_cfg.get("provider", "ollama")
    mode_model = mode_cfg.get("model")  # may be None

    # Resolve registered provider
    if pref in state.providers:
        prov_obj = state.providers[pref]
    elif "ollama" in state.providers:
        prov_obj = state.providers["ollama"]
    else:
        prov_obj = next(iter(state.providers.values())) if state.providers else None

    if prov_obj is None:
        return None

    # If a per-mode model override is set and it differs, clone the provider.
    if mode_model and mode_model != getattr(prov_obj, "model", None):
        api_key = getattr(prov_obj, "api_key", None)
        if api_key is not None:
            try:
                cloned = prov_obj.__class__(api_key=api_key, model=mode_model)
                return cloned
            except Exception:
                pass  # fall through to returning the original

    return prov_obj


def _bootstrap_starter_tags_if_needed(cfg: dict) -> None:
    """On first run: if triggers.tags is absent, write the 5 starter tags to cfg-overlay.

    Idempotent — if tags already exist this is a no-op. Modifies *cfg* in place
    so the rest of build_server_state sees the bootstrapped values.
    """
    if cfg.get("triggers", {}).get("tags"):
        return  # already populated — nothing to do

    from claude_code_talker.triggers.tags import TagLibrary, STARTER_TAGS  # noqa: F401
    import os as _os
    import yaml as _yaml
    from pathlib import Path as _P

    lib = TagLibrary()
    lib.bootstrap_starters()

    overlay_path = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if overlay_path.exists():
        try:
            existing = _yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}

    existing.setdefault("triggers", {})["tags"] = lib.to_cfg()

    tmp = overlay_path.with_suffix(overlay_path.suffix + ".tmp")
    tmp.write_text(_yaml.safe_dump(existing, sort_keys=True), encoding="utf-8")
    _os.replace(tmp, overlay_path)

    # Reflect the bootstrapped tags into the live cfg dict so the daemon
    # doesn't need a second load cycle to see them.
    cfg.setdefault("triggers", {})["tags"] = lib.to_cfg()


def build_server_state(cwd: str | None = None) -> ServerState:
    """Construct the server state with all engines, providers, and modes registered."""
    cfg = load_full_config(cwd=cwd)

    # Phase 14.5 — Bootstrap starter tags on first run (idempotent).
    _bootstrap_starter_tags_if_needed(cfg)

    # Read API keys from ~/.claude/scripts/codetalker/secrets.yaml (env vars
    # always win, so a developer with .env-based setup is unaffected). Loaded
    # ONCE here so providers/engines see consistent values for the daemon's
    # lifetime; user-edited keys take effect on next daemon restart.
    secrets = SecretsStore()

    piper = PiperEngine(piper_exe=PIPER_DIR / "piper.exe", voices_dir=VOICES_DIR)
    ollama = OllamaProvider()

    providers: dict[str, object] = {"ollama": ollama}

    anthropic_cfg = ((cfg.get("providers") or {}).get("anthropic") or {})
    anthropic_key = secrets.get("anthropic_api_key") or os.environ.get(anthropic_cfg.get("api_key_env", "ANTHROPIC_API_KEY"))
    if anthropic_key:
        try:
            from claude_code_talker.providers.anthropic import AnthropicProvider as _Anth
            providers["anthropic"] = _Anth(
                api_key=anthropic_key,
                model=anthropic_cfg.get("model", "claude-haiku-4-5-20251001"),
            )
        except (ImportError, ValueError) as e:
            import logging
            logging.info("anthropic provider unavailable: %s", e)
    else:
        import logging
        logging.info("ANTHROPIC_API_KEY not set; anthropic provider unavailable")

    openrouter_cfg = ((cfg.get("providers") or {}).get("openrouter") or {})
    openrouter_key = secrets.get("openrouter_api_key") or os.environ.get(openrouter_cfg.get("api_key_env", "OPENROUTER_API_KEY"))
    if openrouter_key:
        from claude_code_talker.providers.openrouter import OpenRouterProvider as _OR
        providers["openrouter"] = _OR(
            api_key=openrouter_key,
            # User-locked default 2026-05-03: cheapest fast model for narration.
            model=openrouter_cfg.get("model", "google/gemini-2.0-flash-001"),
        )
    else:
        import logging
        logging.info("OPENROUTER_API_KEY not set; openrouter provider unavailable")

    # OpenAI as an LLM provider (chat completions). Requires `openai` package.
    openai_chat_cfg = ((cfg.get("providers") or {}).get("openai") or {})
    openai_chat_key = secrets.get("openai_api_key") or os.environ.get(openai_chat_cfg.get("api_key_env", "OPENAI_API_KEY"))
    if openai_chat_key:
        try:
            from claude_code_talker.providers.openai_chat import OpenAIChatProvider as _OAIChat
            providers["openai"] = _OAIChat(
                api_key=openai_chat_key,
                model=openai_chat_cfg.get("model", "gpt-4o-mini"),
            )
        except (ImportError, ValueError) as e:
            import logging
            logging.info("openai LLM provider unavailable: %s", e)

    engines: dict[str, object] = {"piper": piper}
    try:
        from claude_code_talker.engines.edge import EdgeEngine as _Edge
        # Only register if the package is actually importable
        import edge_tts  # noqa: F401
        engines["edge"] = _Edge()
    except ImportError:
        import logging
        logging.info("edge-tts not installed; edge engine unavailable")

    elevenlabs_key_env = ((cfg.get("engines") or {}).get("elevenlabs") or {}).get("api_key_env", "ELEVENLABS_API_KEY")
    elevenlabs_key = secrets.get("elevenlabs_api_key") or os.environ.get(elevenlabs_key_env)
    if elevenlabs_key:
        from claude_code_talker.engines.elevenlabs import ElevenLabsEngine as _EL
        engines["elevenlabs"] = _EL(api_key=elevenlabs_key)
    else:
        import logging
        logging.info("ElevenLabs API key not set; engine unavailable")

    openai_key_env = ((cfg.get("engines") or {}).get("openai") or {}).get("api_key_env", "OPENAI_API_KEY")
    openai_key = secrets.get("openai_api_key") or os.environ.get(openai_key_env)
    if openai_key:
        from claude_code_talker.engines.openai import OpenAIEngine as _OAI
        engines["openai"] = _OAI(api_key=openai_key)
    else:
        import logging
        logging.info("OpenAI API key not set; engine unavailable")

    xtts_cfg = ((cfg.get("engines") or {}).get("xtts") or {})
    xtts_refs = Path(xtts_cfg.get("references_dir") or
                     (Path.home() / ".claude" / "scripts" / "voice-cloner" / "references"))
    if xtts_refs.exists():
        try:
            from claude_code_talker.engines.xtts import XTTSEngine as _XTTS
            engines["xtts"] = _XTTS(references_dir=xtts_refs)
        except ImportError:
            import logging
            logging.info("TTS package not installed; xtts engine unavailable")
    else:
        import logging
        logging.info("xtts references dir doesn't exist; xtts engine unavailable")

    live_cfg = cfg.get("live") or {}
    cadence_name = live_cfg.get("cadence", "periodic")
    cadence = make_cadence(cadence_name, live_cfg)

    profiles = ProfileStore()

    state = ServerState(
        cfg=cfg,
        engines=engines,
        providers=providers,
        modes={
            "direct": DirectMode(),
            # brief and live constructed below after _select_provider can resolve
        },
        active_mode=cfg.get("active_mode", "direct"),
    )

    state.profiles = profiles
    state.secrets = secrets
    state.narration_log = NarrationLog()
    state.voice_install_tasks = {}
    state.voice_preview_audio = {}
    state.token_tracker = TokenTracker()
    state.tts_cache = TTSCache()
    state.tuning_history = TuningHistory()
    state.session_focus = SessionFocusRegistry()
    def _on_new_prose(sid: str, prose: str) -> None:
        if state.session_focus is not None:
            state.session_focus.record_assistant_prose(sid, prose)
        live = state.modes.get("live")
        if isinstance(live, LiveMode):
            try:
                live._trigger_handler(sid, prose)
            except Exception as e:
                import logging
                logging.warning("trigger handler failed: %s", e)

    state.transcript_watcher = TranscriptWatcher(on_new_prose=_on_new_prose)
    # Latest virtual-eval report cached in memory for /api/virtual-eval/latest
    state.virtual_eval_latest = None
    persistent_sessions = PersistentSessionStore()
    state.persistent_sessions = persistent_sessions
    from claude_code_talker.characters import CharacterStore
    state.characters = CharacterStore()
    # Phase 25c — voice clone job tracker
    from claude_code_talker.voice.cloning_jobs import CloneJobTracker
    state.clone_jobs = CloneJobTracker(
        Path.home() / ".claude" / "scripts" / "codetalker" / "voice_clone_jobs"
    )
    # Phase 25b — mesh job tracker + storage root for downloaded meshes.
    from claude_code_talker.mesh.tracker import MeshJobTracker
    _mesh_root = Path.home() / ".claude" / "scripts" / "codetalker" / "models"
    state.mesh_models_root = _mesh_root
    state.mesh_jobs = MeshJobTracker(_mesh_root / "_jobs")
    state.sessions = SessionRegistry(
        profile_store=profiles,
        persistent_session_store=persistent_sessions,
        base_cfg_provider=lambda: state.cfg,
        character_store=state.characters,
    )
    state.sessions.start_sweeper(interval_seconds=60.0, max_idle_seconds=1800.0)

    catalog = SessionCatalog()
    catalog.scan()
    state.catalog = catalog
    state.catalog.start_watcher(interval_seconds=30.0)

    state.event_buffer = EventBuffer(max_size=int(live_cfg.get("buffer_size", 30)))
    from claude_code_talker.narration_stream import NarrationStream
    state.narration_stream = NarrationStream()
    state.audio_queue = AudioQueue(
        state,
        max_depth=int(live_cfg.get("queue_max_depth", 5)),
        staleness_seconds=float(live_cfg.get("staleness_seconds", 20.0)),
        narration_stream=state.narration_stream,
    )
    state.audio_queue.start()

    state.modes["brief"] = BriefMode(provider=_select_provider(state, "brief"))
    state.modes["live"] = LiveMode(
        provider=_select_provider(state, "live"),
        cadence=cadence,
        event_buffer=state.event_buffer,
        audio_queue=state.audio_queue,
        cfg=cfg,
        narration_log=state.narration_log,
        sessions=state.sessions,
        session_focus=state.session_focus,
        catalog=state.catalog,
    )
    return state


async def autostart_live_if_configured(state: ServerState) -> None:
    """Start LiveMode's cadence loop so per-session active_mode=live narrates.

    Called from a Starlette startup hook (after the asyncio event loop is up).
    We start the loop but DO NOT change ``state.active_mode`` — the global
    default still falls back to whatever cfg said. Per-session active_mode
    overrides (via profile or live_overlay) decide whether a session's events
    actually feed the cadence narration. Cheap when no session is in live
    mode; disabled sessions are gated upstream at the hook handler.
    """
    live = state.modes.get("live")
    if isinstance(live, LiveMode):
        live.start()
    # Phase 13.9c Task 7 — start continuous transcript watcher (needs asyncio loop).
    if state.transcript_watcher is not None:
        state.transcript_watcher.start()


def main():
    """Entry point for the `claude-code-talker` CLI command.

    Subcommands:
      claude-code-talker          - print status (legacy summary)
      claude-code-talker serve    - run as foreground daemon
      claude-code-talker stop     - send tts_shutdown to running daemon (Task 13)
    """
    import sys
    args = sys.argv[1:]
    if args and args[0] == "serve":
        from claude_code_talker.daemon import serve_foreground
        serve_foreground()
        return
    if args and args[0] == "stop":
        from claude_code_talker.daemon import stop_daemon
        stop_daemon()
        return

    state = build_server_state()
    print(f"claude-code-talker server initialized")
    print(f"  engines: {list(state.engines)}")
    print(f"  providers: {list(state.providers)}")
    print(f"  modes: {list(state.modes)}")
    print(f"  active mode: {state.active_mode}")
    print("Use 'claude-code-talker serve' to start the daemon.")


if __name__ == "__main__":
    main()


from dataclasses import dataclass as _dc


@_dc
class MCPTool:
    name: str
    description: str
    handler: object  # async callable


class MCPServer:
    """Thin server that hosts a registry of named tools and dispatches calls.

    Phase 1: testable in isolation. Phase 2: wire to the official mcp SDK
    transport (stdio/SSE) without changing the tool implementations.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool):
        self._tools[tool.name] = tool

    def list_tools(self):
        return list(self._tools.values())

    async def call_tool(self, name: str, args: dict) -> str:
        if name not in self._tools:
            raise ValueError(f"unknown tool: {name}")
        return await self._tools[name].handler(args)


def register_tools(server, state) -> None:
    """Register all 7 Phase 2A tools on a server instance.

    The server must expose a `.register(MCPTool)` method. This works for both
    our in-process MCPServer (Phase 1, used in tests) and a thin adapter
    around the mcp SDK FastMCP server (production, lands in Phase 2A.3).
    """

    async def tts_speak(args):
        text = args.get("text", "")
        if not text:
            return "skipped: no text"
        if not state.cfg.get("enabled", True):
            return "skipped: muted"
        engine_name = (state.cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        if not engine:
            raise ValueError(f"engine not registered: {engine_name}")
        voice = (state.cfg.get("voice") or {}).get("model")
        rate = float((state.cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices()
            if not voices:
                return "skipped: no voices available"
            voice = voices[0]
        state.audio_queue.submit(AudioJob(text=text, voice=voice, rate=rate, engine_name=engine_name,
                                          audio_format=getattr(engine, "audio_format", "wav")))
        return f"queued: {len(text)} chars"

    async def tts_set_mode(args):
        new_mode = args.get("mode")
        if new_mode not in state.modes:
            raise ValueError(f"unknown mode: {new_mode}; available: {list(state.modes)}")

        # If switching AWAY from live, shut down the cadence loop
        old_mode = state.active_mode
        if old_mode == "live" and new_mode != "live":
            live = state.modes.get("live")
            if isinstance(live, LiveMode):
                await live.shutdown()

        state.active_mode = new_mode

        # If switching TO live, start the cadence loop
        if new_mode == "live":
            live = state.modes.get("live")
            if isinstance(live, LiveMode):
                live.start()

        return f"active mode set to {new_mode}"

    async def tts_status(args):
        enabled = state.cfg.get("enabled", True)
        return (
            f"mode={state.active_mode}, "
            f"{'enabled' if enabled else 'muted'}, "
            f"engines={list(state.engines)}, "
            f"providers={list(state.providers)}"
        )

    async def tts_mute(args):
        state.cfg["enabled"] = False
        return "muted"

    async def tts_unmute(args):
        state.cfg["enabled"] = True
        return "unmuted"

    async def tts_list_voices(args):
        engine_name = args.get("engine") or "piper"
        engine = state.engines.get(engine_name)
        if not engine:
            raise ValueError(f"unknown engine: {engine_name}")
        return ", ".join(engine.list_voices())

    async def tts_shutdown(args):
        state.shutting_down = True
        if state.uvicorn_server is not None:
            state.uvicorn_server.should_exit = True
        return "shutting down"

    async def tts_set_voice(args):
        voice = args.get("voice")
        if not voice:
            raise ValueError("voice is required")
        engine_name = args.get("engine")
        voice_cfg = state.cfg.setdefault("voice", {})
        voice_cfg["model"] = voice
        if engine_name:
            if engine_name not in state.engines:
                raise ValueError(f"unknown engine: {engine_name}; available: {list(state.engines)}")
            voice_cfg["engine"] = engine_name
        return f"voice set to {voice}" + (f" on {engine_name}" if engine_name else "")

    async def tts_set_cadence(args):
        cadence = args.get("cadence")
        valid = ["periodic", "per_tool_call", "per_cluster", "significant_only", "hybrid"]
        if cadence not in valid:
            raise ValueError(f"unknown cadence: {cadence}; valid: {valid}")
        live_cfg = state.cfg.setdefault("live", {})
        live_cfg["cadence"] = cadence
        live = state.modes.get("live")
        if isinstance(live, LiveMode):
            live.cadence = make_cadence(cadence, live_cfg)
        return f"cadence set to {cadence}"

    async def tts_handle_stop(args):
        from claude_code_talker.hooks import handle_stop
        session_id = args.get("session_id") or args.get("cwd") or "_unknown"
        cwd = args.get("cwd", "")
        transcript_path = args.get("transcript_path", "")
        state.sessions.touch(session_id, cwd=cwd, transcript_path=transcript_path)
        # Phase 13.9c Task 7 — register session with transcript watcher on first touch.
        if transcript_path and state.transcript_watcher is not None:
            from pathlib import Path as _Path
            state.transcript_watcher.watch(session_id, _Path(transcript_path))
        s = state.sessions.get(session_id)
        if s is not None and not s.enabled:
            return "skipped: per-session disabled"
        cfg = state.sessions.config_for(session_id)
        if not cfg.get("enabled", True):
            return "skipped: muted"
        text = await handle_stop(
            payload={"transcript_path": transcript_path, "cwd": cwd},
            cfg=cfg,
            mode_a=state.modes.get("direct"),
            mode_b=state.modes.get("brief"),
            active_mode=state.active_mode,
        )
        if not text:
            return "skipped: no text"
        engine_name = (cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        voice = (cfg.get("voice") or {}).get("model")
        rate = float((cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices()
            if not voices:
                return "skipped: no voices"
            voice = voices[0]
        state.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, engine_name=engine_name,
            audio_format=getattr(engine, "audio_format", "wav"),
        ))
        return f"queued: {len(text)} chars"

    async def tts_handle_user_prompt_submit(args):
        import time as _t
        from claude_code_talker.hooks import handle_user_prompt_submit
        session_id = args.get("session_id") or args.get("cwd") or "_unknown"
        cwd = args.get("cwd", "")
        state.sessions.touch(session_id, cwd=cwd)
        # Phase 13.9c Task 7 — register with transcript watcher via catalog lookup.
        if state.transcript_watcher is not None and state.catalog is not None:
            try:
                entry = state.catalog.entry_for(session_id)
                tp = getattr(entry, "transcript_path", None) if entry else None
                if tp:
                    from pathlib import Path as _Path
                    state.transcript_watcher.watch(session_id, _Path(tp))
            except Exception:
                pass  # best-effort; Stop handler will register when transcript_path is in args
        s = state.sessions.get(session_id)
        if s is not None and not s.enabled:
            return "skipped: per-session disabled"
        cfg = state.sessions.config_for(session_id)
        # Push USER_PROMPT into the live buffer so subsequent tool events have
        # the user's intent as context for WHY-focused narration.
        prompt_text = args.get("prompt", "") or ""
        if prompt_text:
            _up_ev = Event(
                timestamp=_t.time(),
                type="USER_PROMPT",
                metadata={"text": prompt_text[:500], "session_id": session_id},
                significance=0.9,
                session_id=session_id,
            )
            state.event_buffer.push(_up_ev)
            if state.session_focus is not None:
                state.session_focus.on_event(session_id, _up_ev)
        provider = _select_provider(state, "brief")  # cheap+fast for one-sentence brief
        text = await handle_user_prompt_submit(
            payload={"prompt": args.get("prompt", "")},
            cfg=cfg, provider=provider,
        )
        if not text:
            return "skipped: no text"
        engine_name = (cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        voice = (cfg.get("voice") or {}).get("model")
        rate = float((cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices() if engine else []
            if not voices:
                return "skipped: no voices"
            voice = voices[0]
        from claude_code_talker.audio import AudioJob
        state.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, engine_name=engine_name,
            audio_format=getattr(engine, "audio_format", "wav"),
            priority="normal",
        ))
        # Also log to narration audit
        if state.narration_log is not None:
            try:
                from claude_code_talker.narration_log import NarrationEntry
                state.narration_log.append(NarrationEntry(
                    timestamp=__import__("time").time(),
                    session_id=session_id,
                    text=text,
                    voice=voice or "",
                    engine=engine_name or "",
                    mode="prompt-brief",
                    priority="normal",
                ))
            except Exception:
                pass
        return f"queued: {len(text)} chars"

    async def tts_handle_notification(args):
        from claude_code_talker.hooks import handle_notification
        session_id = args.get("session_id") or "_unknown"
        state.sessions.touch(session_id)
        s = state.sessions.get(session_id)
        if s is not None and not s.enabled:
            return "skipped: per-session disabled"
        cfg = state.sessions.config_for(session_id)
        text = handle_notification(
            payload={"message": args.get("message", "")},
            cfg=cfg,
        )
        if not text:
            return "skipped: no text"
        engine_name = (cfg.get("voice") or {}).get("engine", "piper")
        engine = state.engines.get(engine_name)
        voice = (cfg.get("voice") or {}).get("model")
        rate = float((cfg.get("voice") or {}).get("rate", 1.0))
        if not voice:
            voices = engine.list_voices()
            if not voices:
                return "skipped: no voices"
            voice = voices[0]
        state.audio_queue.submit(AudioJob(
            text=text, voice=voice, rate=rate, engine_name=engine_name,
            audio_format=getattr(engine, "audio_format", "wav"),
        ))
        return f"queued: {len(text)} chars"

    async def tts_handle_pretool(args):
        import time
        session_id = args.get("session_id") or args.get("cwd") or "_unknown"
        cwd = args.get("cwd", "")
        state.sessions.touch(session_id, cwd=cwd)
        s = state.sessions.get(session_id)
        if s is not None and not s.enabled:
            return "skipped: per-session disabled"
        cfg = state.sessions.config_for(session_id)
        keywords = ((cfg.get("content_filter") or {}).get("speak_keywords") or [])
        ev = Event(
            timestamp=time.time(),
            type="PRE_TOOL",
            metadata={
                "tool_name": args.get("tool_name", ""),
                "input": str(args.get("tool_input", ""))[:200],
            },
            significance=0.0,
            session_id=session_id,
        )
        ev.significance = score_significance(ev, keywords)
        state.event_buffer.push(ev)
        if state.session_focus is not None:
            state.session_focus.on_event(session_id, ev)
        return "recorded"

    async def tts_handle_posttool(args):
        import time
        session_id = args.get("session_id") or args.get("cwd") or "_unknown"
        cwd = args.get("cwd", "")
        state.sessions.touch(session_id, cwd=cwd)
        s = state.sessions.get(session_id)
        if s is not None and not s.enabled:
            return "skipped: per-session disabled"
        cfg = state.sessions.config_for(session_id)
        keywords = ((cfg.get("content_filter") or {}).get("speak_keywords") or [])
        response = args.get("tool_response", {}) or {}
        ev = Event(
            timestamp=time.time(),
            type="POST_TOOL",
            metadata={
                "tool_name": args.get("tool_name", ""),
                "input": str(args.get("tool_input", ""))[:200],
                "response": str(response)[:200],
                "success": response.get("success", True) if isinstance(response, dict) else True,
            },
            significance=0.0,
            session_id=session_id,
        )
        ev.significance = score_significance(ev, keywords)
        state.event_buffer.push(ev)
        return "recorded"

    server.register(MCPTool("tts_speak", "Speak the given text using the active engine.", tts_speak))
    server.register(MCPTool("tts_set_mode", "Switch active mode: direct or brief.", tts_set_mode))
    server.register(MCPTool("tts_status", "Report current state.", tts_status))
    server.register(MCPTool("tts_mute", "Mute TTS without changing config.", tts_mute))
    server.register(MCPTool("tts_unmute", "Unmute TTS.", tts_unmute))
    server.register(MCPTool("tts_list_voices", "List available voices for an engine.", tts_list_voices))
    server.register(MCPTool("tts_set_voice", "Set the active voice (model). Optional engine arg switches engine too.", tts_set_voice))
    server.register(MCPTool("tts_set_cadence", "Set the live-mode cadence (periodic, per_tool_call, per_cluster, significant_only, hybrid).", tts_set_cadence))
    server.register(MCPTool("tts_shutdown", "Gracefully shut down the daemon.", tts_shutdown))
    server.register(MCPTool("tts_handle_stop", "Handle a Stop hook event.", tts_handle_stop))
    server.register(MCPTool("tts_handle_notification", "Handle a Notification hook event.", tts_handle_notification))
    server.register(MCPTool(
        "tts_handle_user_prompt_submit",
        "Handle a UserPromptSubmit hook event: narrate one-sentence brief of what the user just asked.",
        tts_handle_user_prompt_submit,
    ))
    server.register(MCPTool("tts_handle_pretool",
                            "Record a PreToolUse event into the rolling buffer.",
                            tts_handle_pretool))
    server.register(MCPTool("tts_handle_posttool",
                            "Record a PostToolUse event into the rolling buffer.",
                            tts_handle_posttool))


def build_mcp_server(state: ServerState) -> MCPServer:
    """Register the Phase 2A tools on a fresh in-process MCPServer."""
    server = MCPServer()
    register_tools(server, state)
    return server


def _register_tools_fastmcp(fmcp, state) -> None:
    """Register the 9 tools on a FastMCP instance by bridging the in-process handlers.

    Our in-process handlers take a single ``args: dict`` argument.  FastMCP
    introspects function signatures to build Pydantic argument models; using
    ``**kwargs`` causes it to create a schema with a single required ``kwargs``
    field rather than an open schema.  We bypass that by adding each tool
    directly to the tool manager with a hand-crafted ``FuncMetadata`` that
    accepts arbitrary keyword arguments and forwards them as a plain dict.
    """
    from mcp.server.fastmcp.tools.base import Tool as _FastTool
    from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata as _FuncMeta, ArgModelBase as _ArgBase
    from pydantic import ConfigDict as _ConfigDict

    class _OpenArgModel(_ArgBase):
        """Accepts any keyword arguments; passes them through as a plain dict."""
        model_config = _ConfigDict(arbitrary_types_allowed=True, extra="allow")

        def model_dump_one_level(self):
            base = super().model_dump_one_level()
            if self.model_extra:
                base.update(self.model_extra)
            return base

    _open_meta = _FuncMeta(arg_model=_OpenArgModel, wrap_output=False)

    inproc = MCPServer()
    register_tools(inproc, state)

    for tool in inproc.list_tools():
        # Capture tool in closure so each wrapper gets its own reference.
        def _make_wrapper(t: MCPTool):
            async def _handler(**kwargs: object) -> str:
                return await t.handler(kwargs)
            _handler.__name__ = t.name
            _handler.__doc__ = t.description
            return _handler

        wrapper = _make_wrapper(tool)
        fast_tool = _FastTool(
            fn=wrapper,
            name=tool.name,
            description=tool.description,
            parameters={"type": "object", "properties": {}, "additionalProperties": True},
            fn_metadata=_open_meta,
            is_async=True,
        )
        fmcp._tool_manager._tools[tool.name] = fast_tool


def build_asgi_app(state: ServerState, *, disable_transport_security: bool = False):
    """Compose a parent Starlette app from FastMCP + /ui static files + /api routes.

    Routes:
      /sse, /messages   -- MCP-over-SSE (FastMCP)
      /ui/*             -- static frontend served from package's static/ dir
      /api/*            -- REST API for sessions, profiles, status, etc.

    Args:
        state: Populated ServerState from build_server_state().
        disable_transport_security: Set True in tests (ASGI transport has no real
            Host header that satisfies the SDK's DNS-rebinding allowlist).  In
            production the daemon binds to 127.0.0.1 and the allowlist is set
            to the daemon's own address.
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    from claude_code_talker.api import build_routes

    if disable_transport_security:
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    else:
        # Allow only the loopback address the daemon listens on (127.0.0.1:17832).
        # These constants mirror daemon.DAEMON_HOST / DAEMON_PORT; they are not
        # imported from daemon.py to avoid a circular dependency.
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:17832", "127.0.0.1", "localhost"],
        )

    fmcp = FastMCP("claude-code-talker", transport_security=security)
    _register_tools_fastmcp(fmcp, state)
    fmcp_app = fmcp.sse_app()

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    react_dir = Path(__file__).parent / "webui" / "dist"
    # react_dir may not exist if the webui hasn't been built yet — that's fine,
    # we still mount it so a 404 is informative.
    react_dir.mkdir(parents=True, exist_ok=True)

    routes = []
    routes.extend(build_routes(state))
    routes.append(Mount("/ui", app=StaticFiles(directory=str(static_dir), html=True)))
    routes.append(Mount("/ui-react", app=StaticFiles(directory=str(react_dir), html=True)))
    routes.append(Mount("/", app=fmcp_app))  # FastMCP handles /sse and /messages at root

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(app):
        await autostart_live_if_configured(state)
        yield

    return Starlette(routes=routes, lifespan=_lifespan)
