"""Tests for SecretsStore."""
import os
import pytest
from pathlib import Path
from claude_code_talker.secrets_store import SecretsStore, KNOWN_KEYS


@pytest.fixture
def store(tmp_path):
    return SecretsStore(secrets_path=tmp_path / "secrets.yaml")


def test_load_empty_when_no_file(store):
    assert store.load() == {}


def test_save_and_load_roundtrip(store):
    store.save({"anthropic_api_key": "sk-ant-abc", "openai_api_key": "sk-oai-xyz"})
    loaded = store.load()
    assert loaded["anthropic_api_key"] == "sk-ant-abc"
    assert loaded["openai_api_key"] == "sk-oai-xyz"


def test_save_filters_unknown_keys(store):
    store.save({
        "anthropic_api_key": "real-key",
        "weird_unknown_key": "should-be-dropped",
        "another_one": "also-dropped",
    })
    loaded = store.load()
    assert "anthropic_api_key" in loaded
    assert "weird_unknown_key" not in loaded
    assert "another_one" not in loaded


def test_save_filters_empty_strings(store):
    store.save({"anthropic_api_key": "real-key", "openai_api_key": ""})
    loaded = store.load()
    assert loaded == {"anthropic_api_key": "real-key"}


def test_get_env_var_wins_over_file(store, monkeypatch):
    store.save({"anthropic_api_key": "from-file"})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert store.get("anthropic_api_key") == "from-env"


def test_get_falls_back_to_file_when_no_env(store, monkeypatch):
    store.save({"anthropic_api_key": "from-file"})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert store.get("anthropic_api_key") == "from-file"


def test_get_returns_none_when_neither(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert store.get("anthropic_api_key") is None


def test_all_resolved_merges_env_and_file(store, monkeypatch):
    store.save({"anthropic_api_key": "from-file", "openai_api_key": "oai-file"})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    resolved = store.all_resolved()
    assert resolved["anthropic_api_key"] == "from-env"
    assert resolved["openai_api_key"] == "oai-file"


def test_update_deletes_key_on_empty_string(store):
    store.save({"anthropic_api_key": "keep", "openai_api_key": "delete-me"})
    store.update({"openai_api_key": ""})
    loaded = store.load()
    assert loaded == {"anthropic_api_key": "keep"}


def test_update_merges_into_existing(store):
    store.save({"anthropic_api_key": "existing"})
    store.update({"openai_api_key": "new"})
    loaded = store.load()
    assert loaded == {"anthropic_api_key": "existing", "openai_api_key": "new"}


def test_redact_short_string():
    assert SecretsStore.redact("abc") == "***"


def test_redact_long_string():
    assert SecretsStore.redact("sk-ant-1234567890abcd") == "*****************abcd"


def test_redact_none():
    assert SecretsStore.redact(None) is None


def test_save_corrupted_file_returns_empty(store, tmp_path):
    (tmp_path / "secrets.yaml").write_text("{invalid: yaml: [unclosed")
    assert store.load() == {}


def test_known_keys_complete():
    assert "anthropic_api_key" in KNOWN_KEYS
    assert "openai_api_key" in KNOWN_KEYS
    assert "openrouter_api_key" in KNOWN_KEYS
    assert "elevenlabs_api_key" in KNOWN_KEYS


def test_gemini_env_var_takes_precedence(monkeypatch, tmp_path):
    secrets_path = tmp_path / "secrets.yaml"
    secrets_path.write_text("gemini_api_key: file_value\n", encoding="utf-8")
    store = SecretsStore(secrets_path=secrets_path)
    monkeypatch.setenv("GEMINI_API_KEY", "env_value")
    assert store.get("gemini_api_key") == "env_value"
