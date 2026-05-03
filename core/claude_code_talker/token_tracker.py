"""Phase 12: token usage tracking + cost dashboard.

Records LLM token consumption and synthesized cost estimates per session and
per provider. Lets users answer "how much did codetalker cost me today?" and
"which session is burning the most tokens?".

Cost is estimated from a per-model price table (USD per 1M tokens, prompt +
completion). Defaults cover the cheap-tier models codetalker recommends; users
can extend the table via cfg.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEFAULT_USAGE_LOG = Path.home() / ".claude" / "scripts" / "codetalker" / "usage.jsonl"


# USD per 1M tokens. (prompt_per_m, completion_per_m)
DEFAULT_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-mini": (0.25, 1.0),
    "gpt-4o": (2.50, 10.0),
    "gpt-5": (10.0, 30.0),
    # OpenRouter — common cheap defaults
    "google/gemini-2.0-flash-001": (0.075, 0.30),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "anthropic/claude-haiku-4-5": (1.0, 5.0),
    "meta-llama/llama-3.3-70b-instruct": (0.12, 0.30),
    # Local (free)
    "ollama": (0.0, 0.0),
}


@dataclass
class UsageEvent:
    timestamp: float
    session_id: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    purpose: str = ""  # "live" / "brief" / "chat"


class TokenTracker:
    """Append-only usage log + in-memory rollups.

    Thread-safe. Append is fast (single line write). Rollup queries iterate
    the log lines (fine for typical daily use; users with millions of events
    can drop the log into a real DB).
    """

    def __init__(
        self,
        log_path: Path | None = None,
        *,
        price_table: dict[str, tuple[float, float]] | None = None,
    ):
        self._path = log_path if log_path is not None else DEFAULT_USAGE_LOG
        self._prices = dict(DEFAULT_PRICE_TABLE)
        if price_table:
            self._prices.update(price_table)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute USD cost for the given usage at the model's per-1M price.

        Returns 0.0 if the model isn't in the price table (cost unknown vs
        cost-zero are indistinguishable here; users can register their own
        prices via the constructor for full coverage).
        """
        prices = self._prices.get(model)
        if prices is None:
            # Try a common case: OpenRouter prefixes like "openai/gpt-4o-mini"
            # may map to the bare name "gpt-4o-mini".
            if "/" in model:
                bare = model.split("/", 1)[1]
                prices = self._prices.get(bare)
        if prices is None:
            return 0.0
        prompt_p, comp_p = prices
        return (prompt_tokens / 1_000_000) * prompt_p + (completion_tokens / 1_000_000) * comp_p

    def record(
        self,
        *,
        session_id: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        purpose: str = "",
    ) -> UsageEvent:
        cost = self.estimate_cost(model, prompt_tokens, completion_tokens)
        event = UsageEvent(
            timestamp=time.time(),
            session_id=session_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            purpose=purpose,
        )
        line = json.dumps(asdict(event), ensure_ascii=False) + "\n"
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line)
        except OSError as e:
            logging.warning("token tracker write failed: %s", e)
        return event

    def _iter_events(self):
        if not self._path.exists():
            return
        try:
            with self._lock:
                with self._path.open("r", encoding="utf-8") as f:
                    for raw in f:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            d = json.loads(raw)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if isinstance(d, dict):
                            yield d
        except OSError:
            return

    def rollup(self, *, since: float | None = None) -> dict:
        """Return aggregate usage since ``since`` (unix timestamp, defaults to all-time).

        Shape:
            {
                "total_cost_usd": float,
                "total_tokens": int,
                "by_provider": {provider: {tokens, cost}},
                "by_model": {model: {tokens, cost}},
                "by_session": {session_id: {tokens, cost}},
                "by_purpose": {purpose: {tokens, cost}},
                "event_count": int,
            }
        """
        result = {
            "total_cost_usd": 0.0, "total_tokens": 0,
            "by_provider": {}, "by_model": {},
            "by_session": {}, "by_purpose": {}, "event_count": 0,
        }
        for d in self._iter_events():
            if since is not None and d.get("timestamp", 0) < since:
                continue
            tokens = int(d.get("total_tokens", 0))
            cost = float(d.get("cost_usd", 0.0))
            result["total_cost_usd"] += cost
            result["total_tokens"] += tokens
            result["event_count"] += 1
            for axis_key, value in (
                ("by_provider", d.get("provider", "?")),
                ("by_model", d.get("model", "?")),
                ("by_session", d.get("session_id", "?")),
                ("by_purpose", d.get("purpose", "?")),
            ):
                bucket = result[axis_key].setdefault(value, {"tokens": 0, "cost": 0.0})
                bucket["tokens"] += tokens
                bucket["cost"] += cost
        return result
