"""Tests for the X-1 license-verification client.

The interesting logic is the cache-honor decision function and the
key-loading order (env beats file). LicenseClient.start() does
network I/O so the full lifecycle isn't unit-tested here; the
decision-function coverage shapes the policy that the lifecycle
implements.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_code_talker.licensing import (
    _should_honor_cached_entitlement,
    is_pro_feature,
    load_license_key,
    save_license_key,
    LicenseState,
    PRO_FEATURES,
)


GRACE = 24 * 60 * 60  # match LicenseClient default


# ---------------------------------------------------------------------------
# _should_honor_cached_entitlement — fail-mode policy.
# ---------------------------------------------------------------------------


def test_honor_within_grace():
    """Wi-Fi blip 1 hour after last good poll — keep Pro active."""
    assert _should_honor_cached_entitlement(
        now=10_000.0,
        last_validated_at=10_000.0 - 3600.0,    # 1h ago
        grace_window_seconds=GRACE,
    ) is True


def test_honor_at_grace_boundary():
    """Exactly at the grace window — strictly less than means we revoke."""
    assert _should_honor_cached_entitlement(
        now=10_000.0,
        last_validated_at=10_000.0 - GRACE,    # exactly 24h ago
        grace_window_seconds=GRACE,
    ) is False


def test_no_cache_never_honors():
    """A failure with no prior successful validate fails closed."""
    assert _should_honor_cached_entitlement(
        now=10_000.0,
        last_validated_at=0.0,
        grace_window_seconds=GRACE,
    ) is False


def test_zero_grace_disables_caching():
    """grace_window=0 means every failure revokes immediately."""
    assert _should_honor_cached_entitlement(
        now=10_000.0,
        last_validated_at=10_000.0 - 60.0,   # 60s ago
        grace_window_seconds=0.0,
    ) is False


def test_negative_grace_disables_caching():
    """Defensive: a negative grace is treated as 'no grace'."""
    assert _should_honor_cached_entitlement(
        now=10_000.0,
        last_validated_at=10_000.0 - 60.0,
        grace_window_seconds=-1.0,
    ) is False


# ---------------------------------------------------------------------------
# is_pro_feature — the gate every Pro-feature call site uses.
# ---------------------------------------------------------------------------


def test_is_pro_feature_known():
    """The four canonical Pro features all gate."""
    assert is_pro_feature("character_attach") is True
    assert is_pro_feature("voice_clone_create") is True
    assert is_pro_feature("buddy_mode") is True
    assert is_pro_feature("ar_pairing") is True


def test_is_pro_feature_unknown():
    """Unknown feature names are NOT Pro — fail open for unknowns
    so a typo at a callsite doesn't accidentally block a free feature."""
    assert is_pro_feature("definitely_not_a_feature") is False
    assert is_pro_feature("") is False


def test_pro_features_set_is_immutable():
    """PRO_FEATURES is a frozenset — adding to it from a caller raises."""
    assert isinstance(PRO_FEATURES, frozenset)
    with pytest.raises(AttributeError):
        PRO_FEATURES.add("something")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Key loading — env takes precedence over file.
# ---------------------------------------------------------------------------


def test_load_key_from_env(monkeypatch, tmp_path):
    """CT_LICENSE_KEY in env wins, even if a file is also present."""
    # Redirect ~/.claude-code-talker to a temp dir so we don't read a real key.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # Windows equivalent
    (tmp_path / ".claude-code-talker").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude-code-talker" / "license.key").write_text(
        "CT-FILE-BASED\n", encoding="utf-8"
    )
    monkeypatch.setenv("CT_LICENSE_KEY", "CT-ENV-WINS")
    assert load_license_key() == "CT-ENV-WINS"


def test_load_key_from_file(monkeypatch, tmp_path):
    """No env var → read the file."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CT_LICENSE_KEY", raising=False)
    (tmp_path / ".claude-code-talker").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude-code-talker" / "license.key").write_text(
        "CT-FROM-FILE  \n", encoding="utf-8"
    )
    assert load_license_key() == "CT-FROM-FILE"


def test_load_key_returns_empty_when_neither(monkeypatch, tmp_path):
    """Daemon runs in Basic mode when no key configured. Empty string,
    not None — callers use truthiness checks throughout."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CT_LICENSE_KEY", raising=False)
    assert load_license_key() == ""


def test_save_then_load_roundtrip(monkeypatch, tmp_path):
    """save_license_key creates parents and writes the value
    such that load_license_key reads it back unchanged."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CT_LICENSE_KEY", raising=False)
    save_license_key("CT-ROUNDTRIP")
    assert load_license_key() == "CT-ROUNDTRIP"


# ---------------------------------------------------------------------------
# LicenseState defaults — initial pessimism.
# ---------------------------------------------------------------------------


def test_license_state_defaults_to_basic():
    """A fresh LicenseState has pro_active=False — the daemon never grants
    Pro before a successful validate. No 'optimistic' interim state."""
    ls = LicenseState()
    assert ls.pro_active is False
    assert ls.key == ""
    assert ls.last_validated_at == 0.0
    assert ls.last_error is None
    assert ls.user_id is None
