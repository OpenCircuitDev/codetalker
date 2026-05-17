"""
One-time migration: legacy persistent_sessions YAMLs → SessionStore SQLite.

Run modes:

  dry_run=True  (default): reads every YAML, attempts to construct
                a Session, reports what WOULD be migrated and what
                WOULD fail. Writes nothing.

  dry_run=False: makes a tarball backup of the YAML directory,
                then for each valid YAML upserts the corresponding
                Session into the store. YAML files are NOT deleted
                (kept as authoritative fallback until phase 6
                cleanup explicitly removes them).

Conventions:

  - YAML files are at DEFAULT_SESSIONS_DIR (~/.claude/scripts/
    codetalker/sessions/<session_id>.yaml).
  - YAML schema is the legacy live_overlay-nested form documented
    in persistent_sessions.py.
  - Unknown YAML keys are LOGGED but not stored. The migration
    captures real fields; experimental dust gets dropped (the
    user knows because the dry-run report names every dropped key).

Failure handling:
  - Per-YAML failures are isolated. One bad YAML doesn't stop the
    rest of the migration.
  - Failures are collected into MigrationReport.failures with file
    path + reason, surfaced at the end.
"""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from claude_code_talker.schemas import (
    AudioOutput,
    CharacterRef,
    MarkupTreatment,
    NarrationConfig,
    Session,
    VoiceConfig,
)

from .session_store import SessionStore

logger = logging.getLogger(__name__)


# The legacy directory. Mirrors persistent_sessions.DEFAULT_SESSIONS_DIR.
DEFAULT_LEGACY_SESSIONS_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "sessions"


# ---------------------------------------------------------------------------
# Report shape.
# ---------------------------------------------------------------------------


@dataclass
class MigratedSession:
    """One successfully-migrated session."""
    yaml_path: Path
    session_id: str
    display_name: str
    dropped_keys: List[str] = field(default_factory=list)


@dataclass
class MigrationFailure:
    """One YAML that couldn't be migrated."""
    yaml_path: Path
    reason: str


@dataclass
class MigrationReport:
    """Summary of a migration run."""
    dry_run: bool
    yaml_dir: Path
    backup_path: Optional[Path]
    migrated: List[MigratedSession] = field(default_factory=list)
    failures: List[MigrationFailure] = field(default_factory=list)
    total_yaml_files: int = 0

    def summary(self) -> str:
        """Single-line human-readable summary."""
        mode = "dry-run" if self.dry_run else "applied"
        return (
            f"[{mode}] {len(self.migrated)}/{self.total_yaml_files} migrated, "
            f"{len(self.failures)} failed"
        )


# ---------------------------------------------------------------------------
# YAML → Session translation.
#
# Field-by-field with explicit handling of each legacy convention.
# Anything we don't know about lands in MigratedSession.dropped_keys
# so the report surfaces it.
# ---------------------------------------------------------------------------


# Which top-level keys we expect in the legacy YAML format.
# Anything else is "unknown" and logged.
KNOWN_TOP_LEVEL_KEYS = {
    "live_overlay",
    "attached_profile",
    "attached_character",
    "enabled",
    "display_name",
    "last_modified",
    "workspace_group",
    "auto_mode_enabled",
    "audio_outputs",
    "auto_mode_idle_threshold_secs",
    "cwd",
    "pinned",
}

# Within live_overlay, which keys we know how to flatten.
KNOWN_LIVE_OVERLAY_KEYS = {
    "active_mode",
    "voice",
    "paths",
    "code_blocks",
    "live",
    "markup",
    # These promoted-key fallbacks may still exist in older overlays.
    # The persistent_sessions migration lifts them to top level on
    # read, but our migration is read-side too so handle both.
    "pinned",
    "workspace_group",
    "audio_outputs",
    "auto_mode_enabled",
    "auto_mode_idle_threshold_secs",
    "display_name",
}


def _safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    """dict.get that treats explicit None as 'missing' for our purposes."""
    v = d.get(key)
    return default if v is None else v


def _normalize_audio_outputs(raw: Any) -> List[AudioOutput]:
    """
    Legacy audio_outputs is a list of strings. Filter to valid
    AudioOutput literals (desktop / phone / glasses); drop anything
    else with a logged warning.
    """
    if not isinstance(raw, (list, tuple)):
        return ["desktop"]
    valid: List[AudioOutput] = []
    for v in raw:
        if v in ("desktop", "phone", "glasses"):
            valid.append(v)  # type: ignore
        else:
            logger.warning("dropping invalid audio_output value: %r", v)
    return valid or ["desktop"]


def _extract_narration(live_overlay: Dict[str, Any]) -> Tuple[NarrationConfig, List[str]]:
    """
    Pull markup / paths / code_blocks out of live_overlay into a
    NarrationConfig. Returns (config, dropped_keys) where dropped_keys
    names any unrecognized children under markup, paths, or live.
    """
    dropped: List[str] = []

    # Markup
    markup_in = live_overlay.get("markup") or {}
    markup_out: Dict[str, MarkupTreatment] = {}
    if isinstance(markup_in, dict):
        for form, raw in markup_in.items():
            if not isinstance(raw, dict):
                dropped.append(f"markup.{form} (not a dict)")
                continue
            kind = raw.get("kind")
            params = raw.get("params") or {}
            if not kind:
                dropped.append(f"markup.{form} (no kind)")
                continue
            try:
                # NarrationConfig.field_validator will sanity-check
                # form+kind combinations. Construct here, then build
                # NarrationConfig once at the end.
                markup_out[form] = MarkupTreatment(kind=kind, params=dict(params))
            except Exception as e:
                dropped.append(f"markup.{form}: {e}")

    # Paths
    paths_handling: str = "filename"
    paths_in = live_overlay.get("paths") or {}
    if isinstance(paths_in, dict):
        h = paths_in.get("handling")
        if h in ("omit", "filename", "full"):
            paths_handling = h
        elif h:
            dropped.append(f"paths.handling = {h!r}")

    # Code blocks
    code_blocks: str = "stub"
    cb = live_overlay.get("code_blocks")
    if cb in ("stub", "full", "summary"):
        code_blocks = cb
    elif cb:
        dropped.append(f"code_blocks = {cb!r}")

    try:
        return (
            NarrationConfig(
                markup=markup_out,
                paths_handling=paths_handling,  # type: ignore
                code_blocks=code_blocks,  # type: ignore
            ),
            dropped,
        )
    except Exception as e:
        logger.warning("falling back to default NarrationConfig: %s", e)
        return NarrationConfig(), dropped + [f"narration_validation_error: {e}"]


def _extract_voice(live_overlay: Dict[str, Any]) -> VoiceConfig:
    """Pull voice config out of live_overlay; fallback to default."""
    voice_in = live_overlay.get("voice")
    if not isinstance(voice_in, dict):
        return VoiceConfig()
    try:
        return VoiceConfig(
            engine=voice_in.get("engine", "piper"),
            model=voice_in.get("model", ""),
            rate=float(voice_in.get("rate", 1.0)),
        )
    except Exception as e:
        logger.warning("voice config invalid; using default: %s", e)
        return VoiceConfig()


def _extract_active_mode(live_overlay: Dict[str, Any]) -> str:
    """Pull active_mode; fall back to brief if missing or invalid."""
    am = live_overlay.get("active_mode", "brief")
    if am in ("live", "brief", "direct", "teacher"):
        return am
    return "brief"


def _extract_cadence(live_overlay: Dict[str, Any]) -> Optional[str]:
    """Pull live.cadence; None if not specified."""
    live = live_overlay.get("live") or {}
    if not isinstance(live, dict):
        return None
    cad = live.get("cadence")
    if cad in (
        "periodic",
        "per_tool_call",
        "per_cluster",
        "significant_only",
        "hybrid",
    ):
        return cad
    return None


def yaml_to_session(yaml_path: Path) -> Tuple[Session, List[str]]:
    """
    Parse one legacy YAML and convert it to a Session. Returns the
    Session plus a list of dropped/unknown keys (for the migration
    report).

    Raises on parse failure or unrecoverable schema violation. The
    caller wraps this so individual failures don't abort the run.
    """
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{yaml_path.name}: top-level is not a mapping")

    session_id = yaml_path.stem
    dropped: List[str] = []

    # Identify unknown top-level keys.
    for key in data.keys():
        if key not in KNOWN_TOP_LEVEL_KEYS:
            dropped.append(f"top:{key}")

    live_overlay = data.get("live_overlay") or {}
    if not isinstance(live_overlay, dict):
        live_overlay = {}
    for key in live_overlay.keys():
        if key not in KNOWN_LIVE_OVERLAY_KEYS:
            dropped.append(f"live_overlay.{key}")

    # Promoted-keys may appear at top-level OR under live_overlay
    # depending on overlay version. Top-level wins.
    def take(key: str, default: Any = None) -> Any:
        if key in data:
            return data[key]
        if key in live_overlay:
            return live_overlay[key]
        return default

    # Build the narration config from live_overlay markup/paths/code_blocks.
    narration, narration_dropped = _extract_narration(live_overlay)
    dropped.extend(narration_dropped)

    # Build attached_character if present and it's a full record
    # (we don't resolve string IDs here — migration is best-effort).
    attached_character: Optional[CharacterRef] = None
    ac = data.get("attached_character")
    if isinstance(ac, dict):
        try:
            attached_character = CharacterRef.model_validate(ac)
        except Exception as e:
            dropped.append(f"attached_character invalid: {e}")

    session = Session(
        session_id=session_id,
        display_name=_safe_get(data, "display_name") or session_id[:12],
        cwd=data.get("cwd"),
        workspace_group=take("workspace_group"),
        active_mode=_extract_active_mode(live_overlay),  # type: ignore
        cadence=_extract_cadence(live_overlay),  # type: ignore
        enabled=bool(_safe_get(data, "enabled", True)),
        auto_mode_enabled=bool(take("auto_mode_enabled", False)),
        audio_outputs=_normalize_audio_outputs(take("audio_outputs", ["desktop"])),
        voice=_extract_voice(live_overlay),
        narration=narration,
        attached_profile=data.get("attached_profile"),
        attached_character=attached_character,
        last_modified=float(_safe_get(data, "last_modified", 0.0) or 0.0),
        pinned=bool(take("pinned", False)),
    )
    return session, dropped


# ---------------------------------------------------------------------------
# Top-level runner.
# ---------------------------------------------------------------------------


def migrate(
    store: SessionStore,
    yaml_dir: Path = DEFAULT_LEGACY_SESSIONS_DIR,
    *,
    dry_run: bool = True,
    backup_dir: Optional[Path] = None,
) -> MigrationReport:
    """
    Migrate all YAMLs in `yaml_dir` into `store`.

    Returns a MigrationReport with per-file outcomes. When dry_run
    is True (default), no writes happen — the report is preview-only.

    backup_dir, when provided, names where the YAML tarball is
    written before any disk modification. Defaults to a sibling
    directory of yaml_dir with a timestamp.
    """
    if not yaml_dir.exists():
        return MigrationReport(
            dry_run=dry_run, yaml_dir=yaml_dir, backup_path=None, total_yaml_files=0
        )

    yaml_files = sorted(yaml_dir.glob("*.yaml"))
    report = MigrationReport(
        dry_run=dry_run,
        yaml_dir=yaml_dir,
        backup_path=None,
        total_yaml_files=len(yaml_files),
    )

    # Backup BEFORE any write. Pure dry-run skips backup since
    # nothing changes.
    if not dry_run:
        backup_dir = backup_dir or yaml_dir.parent / (
            f"sessions_backup_{int(time.time())}"
        )
        shutil.copytree(yaml_dir, backup_dir)
        report.backup_path = backup_dir
        logger.info("backed up %s → %s", yaml_dir, backup_dir)

    for yp in yaml_files:
        try:
            session, dropped = yaml_to_session(yp)
        except Exception as e:
            report.failures.append(
                MigrationFailure(yaml_path=yp, reason=f"{type(e).__name__}: {e}")
            )
            continue

        if not dry_run:
            try:
                store.upsert(session)
            except Exception as e:
                report.failures.append(
                    MigrationFailure(
                        yaml_path=yp, reason=f"upsert: {type(e).__name__}: {e}"
                    )
                )
                continue

        report.migrated.append(
            MigratedSession(
                yaml_path=yp,
                session_id=session.session_id,
                display_name=session.display_name,
                dropped_keys=dropped,
            )
        )

    return report


# ---------------------------------------------------------------------------
# CLI entry — runnable as `python -m claude_code_talker.store.migrate_yaml`.
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate legacy YAML session overlays to SessionStore SQLite."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path.home() / ".claude" / "scripts" / "codetalker" / "sessions.db",
        help="Target SQLite database file (will be created if missing).",
    )
    parser.add_argument(
        "--yaml-dir",
        type=Path,
        default=DEFAULT_LEGACY_SESSIONS_DIR,
        help="Source directory of YAML overlay files.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the migration. Without this flag, runs in dry-run mode.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    store = SessionStore(args.db)
    try:
        report = migrate(store, args.yaml_dir, dry_run=not args.apply)
    finally:
        store.close()

    print(report.summary())
    if report.backup_path:
        print(f"backup: {report.backup_path}")
    if report.failures:
        print(f"\n{len(report.failures)} failures:")
        for f in report.failures[:20]:
            print(f"  {f.yaml_path.name}: {f.reason}")
        if len(report.failures) > 20:
            print(f"  ... and {len(report.failures) - 20} more")

    # If there were any dropped keys, surface a summary across the migration.
    total_dropped = sum(len(m.dropped_keys) for m in report.migrated)
    if total_dropped:
        unique_drops: Dict[str, int] = {}
        for m in report.migrated:
            for d in m.dropped_keys:
                unique_drops[d] = unique_drops.get(d, 0) + 1
        print(f"\n{total_dropped} dropped/unknown keys across migrated files:")
        for key, count in sorted(unique_drops.items(), key=lambda x: -x[1])[:30]:
            print(f"  {count:>4}  {key}")


if __name__ == "__main__":
    _cli()
