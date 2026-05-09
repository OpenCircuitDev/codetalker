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
