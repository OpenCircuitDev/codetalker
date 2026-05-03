"""Phase 10: TTS cache.

Caches synthesized audio bytes keyed on the inputs that uniquely determine the
output: (text, voice, engine_name, rate, audio_format). Cache lives on disk so
it survives daemon restarts; bytes can be 100KB-2MB per clip so memory caching
is the wrong shape.

Two-level layout:
    ~/.claude/scripts/codetalker/tts_cache/
        <engine>/<sha256[:2]>/<sha256>.<ext>

Sharding by first two hex chars keeps any one directory under ~4K entries even
at very large cache sizes.

A simple LRU eviction (by file mtime) caps total cache size at a configurable
byte budget (default 200MB).
"""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CACHE_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "tts_cache"
DEFAULT_MAX_BYTES = 200 * 1024 * 1024  # 200 MB


@dataclass(frozen=True)
class CacheKey:
    text: str
    voice: str
    engine_name: str
    rate: float
    audio_format: str

    def to_hash(self) -> str:
        material = f"{self.engine_name}|{self.voice}|{self.rate:.4f}|{self.audio_format}|{self.text}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


class TTSCache:
    """Filesystem-backed cache of synthesized audio bytes.

    Thread-safe (RLock). LRU eviction is best-effort and fires on save() when
    the directory total exceeds ``max_bytes``. Reads are O(1) (single stat +
    read). Hits update the file mtime so they stay alive in the LRU window.
    """

    def __init__(self, cache_dir: Path | None = None, *, max_bytes: int = DEFAULT_MAX_BYTES):
        self._dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
        self._max_bytes = max_bytes
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _path_for(self, key: CacheKey) -> Path:
        h = key.to_hash()
        return self._dir / key.engine_name / h[:2] / f"{h}.{key.audio_format}"

    def get(self, key: CacheKey) -> bytes | None:
        path = self._path_for(key)
        with self._lock:
            if not path.exists():
                self._misses += 1
                return None
            try:
                data = path.read_bytes()
            except OSError as e:
                logging.warning("tts cache read failed for %s: %s", path, e)
                self._misses += 1
                return None
            # Touch mtime so this entry is considered recently used.
            try:
                path.touch()
            except OSError:
                pass
            self._hits += 1
            return data

    def put(self, key: CacheKey, audio_bytes: bytes) -> Path:
        if not audio_bytes:
            raise ValueError("refusing to cache empty audio bytes")
        path = self._path_for(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            try:
                tmp.write_bytes(audio_bytes)
                tmp.replace(path)
            except OSError:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
                raise
            self._maybe_evict_locked()
        return path

    def stats(self) -> dict:
        total_bytes = 0
        entry_count = 0
        if self._dir.exists():
            for f in self._dir.rglob("*"):
                if f.is_file() and not f.name.endswith(".tmp"):
                    try:
                        total_bytes += f.stat().st_size
                        entry_count += 1
                    except OSError:
                        pass
        with self._lock:
            return {
                "entries": entry_count,
                "bytes": total_bytes,
                "max_bytes": self._max_bytes,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": (self._hits / (self._hits + self._misses)) if (self._hits + self._misses) else 0.0,
            }

    def clear(self) -> int:
        """Remove all cached entries. Returns number of files deleted."""
        deleted = 0
        if not self._dir.exists():
            return 0
        with self._lock:
            for f in list(self._dir.rglob("*")):
                if f.is_file():
                    try:
                        f.unlink()
                        deleted += 1
                    except OSError:
                        pass
        return deleted

    def _maybe_evict_locked(self) -> int:
        """Caller holds self._lock. Evict oldest-by-mtime until under budget."""
        if not self._dir.exists():
            return 0
        files: list[tuple[float, int, Path]] = []
        total = 0
        for f in self._dir.rglob("*"):
            if not f.is_file() or f.name.endswith(".tmp"):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, f))
            total += st.st_size
        if total <= self._max_bytes:
            return 0
        # Oldest-first
        files.sort(key=lambda t: t[0])
        evicted = 0
        for _, size, path in files:
            if total <= self._max_bytes:
                break
            try:
                path.unlink()
                total -= size
                evicted += 1
            except OSError:
                continue
        return evicted
