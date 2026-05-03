"""Tests for TTSCache."""
import time
import pytest
from pathlib import Path
from claude_code_talker.tts_cache import TTSCache, CacheKey


@pytest.fixture
def cache(tmp_path):
    return TTSCache(cache_dir=tmp_path / "tts_cache", max_bytes=10 * 1024)


def make_key(text="hello", voice="jenny", engine="piper", rate=1.0, fmt="wav"):
    return CacheKey(text=text, voice=voice, engine_name=engine, rate=rate, audio_format=fmt)


def test_get_miss_returns_none(cache):
    assert cache.get(make_key()) is None


def test_put_then_get_roundtrip(cache):
    k = make_key()
    cache.put(k, b"audio-bytes-here")
    assert cache.get(k) == b"audio-bytes-here"


def test_different_keys_isolated(cache):
    k1 = make_key(text="hello")
    k2 = make_key(text="goodbye")
    cache.put(k1, b"hello-audio")
    cache.put(k2, b"goodbye-audio")
    assert cache.get(k1) == b"hello-audio"
    assert cache.get(k2) == b"goodbye-audio"


def test_voice_change_is_different_key(cache):
    k1 = make_key(voice="jenny")
    k2 = make_key(voice="marvin")
    cache.put(k1, b"jenny-clip")
    assert cache.get(k2) is None


def test_rate_change_is_different_key(cache):
    k1 = make_key(rate=1.0)
    k2 = make_key(rate=1.5)
    cache.put(k1, b"normal")
    assert cache.get(k2) is None


def test_engine_change_is_different_key(cache):
    k1 = make_key(engine="piper")
    k2 = make_key(engine="edge")
    cache.put(k1, b"piper-bytes")
    assert cache.get(k2) is None


def test_put_rejects_empty_bytes(cache):
    with pytest.raises(ValueError):
        cache.put(make_key(), b"")


def test_stats_tracks_hits_and_misses(cache):
    k = make_key()
    cache.get(k)        # miss
    cache.put(k, b"x" * 100)
    cache.get(k)        # hit
    cache.get(k)        # hit
    s = cache.stats()
    assert s["hits"] == 2
    assert s["misses"] == 1
    assert s["entries"] == 1


def test_clear_removes_all_entries(cache):
    cache.put(make_key(text="a"), b"x" * 100)
    cache.put(make_key(text="b"), b"y" * 100)
    deleted = cache.clear()
    assert deleted == 2
    assert cache.get(make_key(text="a")) is None


def test_eviction_keeps_under_budget(tmp_path):
    cache = TTSCache(cache_dir=tmp_path, max_bytes=300)
    cache.put(make_key(text="a"), b"x" * 100)
    time.sleep(0.05)
    cache.put(make_key(text="b"), b"x" * 100)
    time.sleep(0.05)
    cache.put(make_key(text="c"), b"x" * 100)
    time.sleep(0.05)
    # Now over budget — adding another should evict oldest
    cache.put(make_key(text="d"), b"x" * 100)
    s = cache.stats()
    assert s["bytes"] <= 300
    # 'a' (oldest) should be gone, 'd' (newest) should be present
    assert cache.get(make_key(text="a")) is None
    assert cache.get(make_key(text="d")) is not None


def test_get_touches_mtime_for_lru(tmp_path):
    cache = TTSCache(cache_dir=tmp_path, max_bytes=300)
    cache.put(make_key(text="oldish"), b"x" * 100)
    time.sleep(0.1)
    cache.put(make_key(text="middle"), b"x" * 100)
    time.sleep(0.1)
    # Access 'oldish' so it becomes recent
    cache.get(make_key(text="oldish"))
    time.sleep(0.05)
    cache.put(make_key(text="newest"), b"x" * 100)
    cache.put(make_key(text="trigger"), b"x" * 100)  # over budget
    # 'middle' should be evicted (no recent touch); 'oldish' (touched) should survive
    assert cache.get(make_key(text="middle")) is None
    assert cache.get(make_key(text="oldish")) is not None


def test_cache_key_hash_deterministic():
    k1 = CacheKey(text="hello", voice="v", engine_name="piper", rate=1.0, audio_format="wav")
    k2 = CacheKey(text="hello", voice="v", engine_name="piper", rate=1.0, audio_format="wav")
    assert k1.to_hash() == k2.to_hash()
    k3 = CacheKey(text="goodbye", voice="v", engine_name="piper", rate=1.0, audio_format="wav")
    assert k1.to_hash() != k3.to_hash()
