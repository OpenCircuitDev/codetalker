import pytest
import json
import asyncio
from pathlib import Path
from claude_code_talker.transcript_watcher import TranscriptWatcher


@pytest.mark.asyncio
async def test_watch_and_scan_picks_up_new_user_prompt(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text("")
    watcher = TranscriptWatcher(poll_interval=0.05)
    watcher.watch("s1", f)
    # Append a user message
    f.write_text(json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n",
                 encoding="utf-8")
    watcher._scan_one("s1", watcher._files["s1"])
    assert watcher._files["s1"].cached_user_prompts == ["hello"]


@pytest.mark.asyncio
async def test_scan_picks_up_assistant_prose(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "thinking about it"}
    ]}}) + "\n", encoding="utf-8")
    watcher = TranscriptWatcher(poll_interval=0.05)
    watcher.watch("s1", f)
    watcher._scan_one("s1", watcher._files["s1"])
    cache = watcher.get_cached_prose("s1")
    assert cache == ["thinking about it"]


@pytest.mark.asyncio
async def test_scan_skips_ide_prefixes(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "<system-reminder>noise</system-reminder>"},
        {"type": "text", "text": "actual prose"},
    ]}}) + "\n", encoding="utf-8")
    watcher = TranscriptWatcher(poll_interval=0.05)
    watcher.watch("s1", f)
    watcher._scan_one("s1", watcher._files["s1"])
    cache = watcher.get_cached_prose("s1")
    assert len(cache) == 1
    assert "noise" not in cache[0]
    assert "actual prose" in cache[0]


@pytest.mark.asyncio
async def test_scan_idempotent_when_no_changes(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "msg1"}
    ]}}) + "\n", encoding="utf-8")
    watcher = TranscriptWatcher(poll_interval=0.05)
    watcher.watch("s1", f)
    watcher._scan_one("s1", watcher._files["s1"])
    watcher._scan_one("s1", watcher._files["s1"])  # second call, no file change
    assert len(watcher.get_cached_prose("s1")) == 1


@pytest.mark.asyncio
async def test_scan_picks_up_appended_lines(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "first"}
    ]}}) + "\n", encoding="utf-8")
    watcher = TranscriptWatcher(poll_interval=0.05)
    watcher.watch("s1", f)
    watcher._scan_one("s1", watcher._files["s1"])
    # Append another line
    with f.open("a", encoding="utf-8") as af:
        af.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "second"}
        ]}}) + "\n")
    watcher._scan_one("s1", watcher._files["s1"])
    cache = watcher.get_cached_prose("s1")
    assert cache == ["first", "second"]


@pytest.mark.asyncio
async def test_callbacks_fire_on_new_content(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text("")
    user_calls = []
    prose_calls = []
    watcher = TranscriptWatcher(
        poll_interval=0.05,
        on_new_user_prompt=lambda sid, t: user_calls.append((sid, t)),
        on_new_prose=lambda sid, t: prose_calls.append((sid, t)),
    )
    watcher.watch("s1", f)
    f.write_text(
        json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hey"}]}}) + "\n",
        encoding="utf-8",
    )
    watcher._scan_one("s1", watcher._files["s1"])
    assert ("s1", "hi") in user_calls
    assert any(c[0] == "s1" and "hey" in c[1] for c in prose_calls)


@pytest.mark.asyncio
async def test_max_prose_caps(tmp_path):
    f = tmp_path / "sess.jsonl"
    lines = "\n".join(
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": f"msg{i}"}]}})
        for i in range(100)
    )
    f.write_text(lines + "\n", encoding="utf-8")
    watcher = TranscriptWatcher(poll_interval=0.05, max_prose_per_session=20)
    watcher.watch("s1", f)
    watcher._scan_one("s1", watcher._files["s1"])
    cache = watcher.get_cached_prose("s1")
    assert len(cache) == 20
    assert cache[-1] == "msg99"  # newest preserved


@pytest.mark.asyncio
async def test_start_stop_lifecycle(tmp_path):
    watcher = TranscriptWatcher(poll_interval=0.05)
    watcher.start()
    await asyncio.sleep(0.1)
    assert watcher._task is not None
    await watcher.stop()
    assert watcher._task is None
