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
