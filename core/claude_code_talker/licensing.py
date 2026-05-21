"""Pro entitlement check via codetalker-website license keys.

The daemon does NOT issue keys — that's the website's job (issued on
Stripe checkout.session.completed webhook). The daemon's role is to
read whichever key the user has stored locally, ask the website
whether it's still valid, cache the answer, and gate Pro features on
that answer.

See: docs/superpowers/decisions/x-1-license-verification.md

## Storage

The key lives at ``~/.claude-code-talker/license.key`` as a single
plaintext line, no surrounding JSON. POST'ing to
``/api/license/activate`` writes it; the file is the only persistent
state this module keeps.

Operators can also set ``CT_LICENSE_KEY`` in the environment for
machines without a writable home directory (CI runners, Docker
containers, etc.).

## Lifecycle

  1. ``LicenseClient(state).start()`` from the daemon's autostart hook.
  2. The client immediately runs a `validate_now()` against the current
     key. The first validation populates `state.licensing` synchronously
     so feature gates can check `state.licensing.pro_active` from the
     very first request.
  3. A background asyncio task re-polls every ``poll_interval_seconds``
     and updates `state.licensing` in place.
  4. ``shutdown()`` cancels the task on daemon stop.

## Failure handling

A validate failure does NOT immediately revoke entitlement. The pure
decision `_should_honor_cached_entitlement` checks how long it's been
since the last successful validation; if that's inside the
``grace_window_seconds`` (default 24h), we keep `pro_active=True` so
a Wi-Fi hiccup doesn't take down Pro features. Beyond the grace
window, we fail-closed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import urllib.request
    import urllib.error
except ImportError:  # pragma: no cover — stdlib always present
    urllib = None  # type: ignore

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure data
# ---------------------------------------------------------------------------


@dataclass
class LicenseState:
    """Current entitlement snapshot. Mutated in place by LicenseClient."""

    # The key as loaded from disk/env. Empty string when none configured.
    key: str = ""
    # Whether Pro features should be allowed right now.
    pro_active: bool = False
    # Unix timestamp of the most recent successful validate call. 0 when
    # we've never had one.
    last_validated_at: float = 0.0
    # Unix timestamp of the most recent validate attempt (success or fail).
    last_attempt_at: float = 0.0
    # Last error message, if any. Cleared on next success.
    last_error: Optional[str] = None
    # User id returned by the website on a successful validate, useful for
    # the webui to show whose subscription this is.
    user_id: Optional[int] = None
    # Machine id we sent on activation. Stable per host; allows the user to
    # see which machines are using their license from the account dashboard.
    machine_id: str = ""


# ---------------------------------------------------------------------------
# Pure decision: should the cached entitlement still be honored?
# ---------------------------------------------------------------------------


def _should_honor_cached_entitlement(
    *,
    now: float,
    last_validated_at: float,
    grace_window_seconds: float,
) -> bool:
    """Pure function: do we keep pro_active=True after a failed poll?

    The fail-mode policy from the decision doc:
        - Within grace_window of last_validated_at → honor cache.
        - Beyond grace_window → revoke immediately.
        - Never validated successfully → never honor (return False).
    """
    if last_validated_at <= 0:
        return False
    if grace_window_seconds <= 0:
        return False
    return (now - last_validated_at) < grace_window_seconds


# ---------------------------------------------------------------------------
# Pro-feature gate
# ---------------------------------------------------------------------------

# 2026-05-18 — initial Pro feature inventory. The decision doc Q1 invites
# the operator to confirm; this is the starting set.
#
# Each entry maps a feature name (used by callers) to a one-line rationale
# for being Pro vs Free. The set is small on purpose — gate the high-cost
# or differentiated experiences, not the operational basics.
PRO_FEATURES: frozenset[str] = frozenset({
    "character_attach",      # Per-session 3D avatar + cloned voice attachment
    "voice_clone_create",    # XTTS local voice cloning from user samples
    "buddy_mode",            # Conversational OpenRouter layer through phone
    "direct_stt",            # Voice-to-Claude dictation via the companion app
    "ar_pairing",            # XREAL glasses + Android companion pairing (gates new tokens;
                             # existing tokens keep working, so a paired device that
                             # falls off Pro continues to function until its token rotates)
    "multi_session_fanin",   # Phone receiving multiple session audio streams in parallel.
                             # Transitively gated by ar_pairing (no paired phone → no
                             # fan-in is possible), but listed explicitly so a future
                             # tier split ("phone-basic = 1 session, phone-pro = N")
                             # has a name to gate on.
})


def is_pro_feature(feature: str) -> bool:
    """Return True when `feature` requires a Pro entitlement.

    Callers pair this with ``state.licensing.pro_active`` to gate:

        if is_pro_feature("voice_clone_create") and not state.licensing.pro_active:
            raise PermissionError("Pro subscription required for voice cloning")
    """
    return feature in PRO_FEATURES


# ---------------------------------------------------------------------------
# Gate helper — returns JSONResponse body+status when the gate fires, else None.
# ---------------------------------------------------------------------------


def pro_gate_payload(feature: str, state) -> Optional[dict]:
    """Standard 402 body for a Pro-gated route. Returns None when the
    request should pass through (feature not Pro, or Pro is active).

    Usage in a Starlette handler:

        gate = pro_gate_payload("voice_clone_create", state)
        if gate is not None:
            return JSONResponse(gate, status_code=402)

    Single body shape so the webui + Android can match on `feature` +
    show a consistent upgrade prompt without per-route conditionals.
    """
    if not is_pro_feature(feature):
        return None
    ls = getattr(state, "licensing", None)
    if ls is not None and ls.pro_active:
        return None
    return {
        "error": "Pro subscription required",
        "feature": feature,
        "upgrade_url": "https://codetalker.opencircuit.studio/pricing",
        "license_status": "active" if (ls and ls.pro_active) else "missing_or_invalid",
    }


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _license_file_path() -> Path:
    """Where the license key file lives on this host."""
    return Path.home() / ".claude-code-talker" / "license.key"


def load_license_key() -> str:
    """Read the license key from env or the per-user file.

    Returns empty string when neither source provides one — the daemon
    then runs in Basic mode (pro_active=False forever).
    """
    env_key = (os.environ.get("CT_LICENSE_KEY") or "").strip()
    if env_key:
        return env_key
    path = _license_file_path()
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except Exception as e:
        log.warning("licensing: failed to read %s: %s", path, e)
        return ""


def save_license_key(key: str) -> None:
    """Persist the key to the per-user file. Creates parents as needed."""
    path = _license_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip() + "\n", encoding="utf-8")
    try:
        # Restrictive perms — only the current user can read.
        # On Windows this is a no-op; on POSIX it matters.
        os.chmod(path, 0o600)
    except Exception:
        pass


def _machine_id() -> str:
    """Stable per-host identifier for license tracking.

    Not a security boundary — anyone can forge a machine_id. The
    purpose is to populate the account dashboard's "machines using
    this license" list so the customer can spot real abuse and
    deactivate stale entries.
    """
    return f"{platform.node()}-{platform.system().lower()}"


# ---------------------------------------------------------------------------
# Remote validation
# ---------------------------------------------------------------------------


def validate_remote(
    *,
    key: str,
    machine_id: str,
    base_url: str,
    timeout_seconds: float = 10.0,
) -> dict:
    """POST {license_key, machine_id} to /api/licenses/validate.

    Returns the parsed JSON response. Raises on network errors or
    non-2xx HTTP. The website's contract:

        Response 200 — { "valid": bool, "user_id"?: int, "error"?: str }

    A 200 with valid=False means the key was syntactically OK but
    the subscription isn't active (cancelled, expired, etc). Treat
    differently from a 5xx/network failure — the first is decisive,
    the second is transient.
    """
    url = base_url.rstrip("/") + "/api/licenses/validate"
    body = json.dumps({"license_key": key, "machine_id": machine_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "codetalker-daemon"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"validate HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"validate network error: {e.reason}") from e


# ---------------------------------------------------------------------------
# Polling client
# ---------------------------------------------------------------------------


class LicenseClient:
    """Owns the LicenseState and the periodic-refresh background task.

    Lifecycle mirrors LiveMode + BriefQuietStretchLoop:

        client = LicenseClient(state)
        client.start()      # synchronous first validate + start poll task
        ...
        await client.shutdown()
    """

    DEFAULT_BASE_URL = "https://codetalker.opencircuit.studio"
    DEFAULT_POLL_INTERVAL_SECONDS = 6 * 60 * 60   # 6 hours
    DEFAULT_GRACE_WINDOW_SECONDS = 24 * 60 * 60   # 24 hours

    def __init__(self, state):
        self.state = state
        self.state.licensing = LicenseState(machine_id=_machine_id())
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Config readers
    # ------------------------------------------------------------------

    def _cfg(self) -> dict:
        return (self.state.cfg or {}).get("licensing") or {}

    def _base_url(self) -> str:
        return str(self._cfg().get("base_url") or self.DEFAULT_BASE_URL)

    def _poll_interval(self) -> float:
        return float(self._cfg().get("poll_interval_seconds", self.DEFAULT_POLL_INTERVAL_SECONDS))

    def _grace_window(self) -> float:
        return float(self._cfg().get("grace_window_seconds", self.DEFAULT_GRACE_WINDOW_SECONDS))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Sync first-validate, then start the periodic poll task."""
        key = load_license_key()
        self.state.licensing.key = key
        if key:
            self._validate_sync(key)
        else:
            self.state.licensing.pro_active = False
            self.state.licensing.last_error = None
            log.info("licensing: no license key configured — running in Basic mode")
        # Start the background loop (does nothing while key is empty).
        if self._task is None:
            self._task = asyncio.create_task(self._poll_loop())

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------
    # Activation (POST /api/license/activate target)
    # ------------------------------------------------------------------

    def activate(self, key: str) -> dict:
        """Persist a new key + validate immediately. Returns the response payload.

        Called from POST /api/license/activate. Caller is responsible
        for surfacing the response to the user.
        """
        key = (key or "").strip()
        if not key:
            self.state.licensing.key = ""
            self.state.licensing.pro_active = False
            try:
                _license_file_path().unlink(missing_ok=True)
            except Exception:
                pass
            return {"valid": False, "error": "empty key"}
        save_license_key(key)
        self.state.licensing.key = key
        return self._validate_sync(key)

    # ------------------------------------------------------------------
    # Validation logic
    # ------------------------------------------------------------------

    def _validate_sync(self, key: str) -> dict:
        """One synchronous validation. Updates state in place."""
        now = time.time()
        self.state.licensing.last_attempt_at = now
        try:
            payload = validate_remote(
                key=key,
                machine_id=self.state.licensing.machine_id,
                base_url=self._base_url(),
            )
        except Exception as e:
            self.state.licensing.last_error = str(e)
            honor = _should_honor_cached_entitlement(
                now=now,
                last_validated_at=self.state.licensing.last_validated_at,
                grace_window_seconds=self._grace_window(),
            )
            if not honor:
                self.state.licensing.pro_active = False
                log.warning(
                    "licensing: validate failed (%s) and no cache — Pro disabled", e
                )
            else:
                log.warning(
                    "licensing: validate failed (%s) but within grace window — Pro stays active", e
                )
            return {"valid": self.state.licensing.pro_active, "error": str(e)}

        # Successful HTTP — decisive answer.
        valid = bool(payload.get("valid"))
        self.state.licensing.pro_active = valid
        self.state.licensing.last_error = None if valid else payload.get("error")
        if valid:
            self.state.licensing.last_validated_at = now
            self.state.licensing.user_id = payload.get("user_id")
            log.info("licensing: validated (user_id=%s)", payload.get("user_id"))
        else:
            log.info("licensing: not valid — %s", payload.get("error"))
        return payload

    async def _poll_loop(self) -> None:
        """Background task: re-validate every poll_interval_seconds."""
        # Small delay so the initial sync validate is what populates state.
        await asyncio.sleep(self._poll_interval())
        while True:
            try:
                key = self.state.licensing.key
                if key:
                    # Run in a thread so urllib doesn't block the event loop.
                    await asyncio.to_thread(self._validate_sync, key)
                await asyncio.sleep(self._poll_interval())
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("licensing: poll loop iteration failed: %s", e)
                # Don't spin — back off the full interval.
                try:
                    await asyncio.sleep(self._poll_interval())
                except asyncio.CancelledError:
                    break
