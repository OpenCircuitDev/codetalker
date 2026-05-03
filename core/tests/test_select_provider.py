"""Tests for _select_provider per-mode model cloning (Sub-task 2.2)."""
import pytest
from unittest.mock import MagicMock
from claude_code_talker.server import _select_provider, ServerState
from claude_code_talker.providers.openrouter import OpenRouterProvider


def _make_state(providers=None, cfg=None):
    """Build a minimal ServerState for testing _select_provider."""
    state = MagicMock(spec=ServerState)
    state.providers = providers or {}
    state.cfg = cfg or {}
    return state


class FakeProvider:
    """Simple provider that accepts (api_key, model) like the real ones."""
    name = "fake"

    def __init__(self, api_key: str, model: str = "default-model"):
        self.api_key = api_key
        self.model = model


# ---------------------------------------------------------------------------
# 1. Returns clone when model is overridden
# ---------------------------------------------------------------------------

def test_select_provider_returns_clone_when_model_overridden():
    """When cfg.modes.live.model differs from registered provider.model, a clone is returned."""
    registered = FakeProvider(api_key="sk-test", model="model-A")
    state = _make_state(
        providers={"fake": registered},
        cfg={"modes": {"live": {"provider": "fake", "model": "model-B"}}},
    )
    result = _select_provider(state, "live")
    assert result is not registered, "Expected a new clone, not the registered instance"
    assert result.model == "model-B"
    assert result.api_key == "sk-test"


def test_select_provider_returns_clone_with_overridden_model_openrouter():
    """Clone works with a real OpenRouterProvider-shaped class."""
    class FakeOR:
        name = "openrouter"
        api_key = "or-key"
        model = "google/gemini-2.0-flash-001"

        def __init__(self, api_key, model="google/gemini-2.0-flash-001"):
            self.api_key = api_key
            self.model = model

    registered = FakeOR(api_key="or-key")
    state = _make_state(
        providers={"openrouter": registered},
        cfg={"modes": {"live": {"provider": "openrouter", "model": "anthropic/claude-haiku-4-5"}}},
    )
    result = _select_provider(state, "live")
    assert result is not registered
    assert result.model == "anthropic/claude-haiku-4-5"
    assert result.api_key == "or-key"


# ---------------------------------------------------------------------------
# 2. Returns registered instance unchanged when no model override
# ---------------------------------------------------------------------------

def test_select_provider_returns_registered_when_no_override():
    """No model in cfg.modes → returns the same registered instance."""
    registered = FakeProvider(api_key="sk-test", model="model-A")
    state = _make_state(
        providers={"fake": registered},
        cfg={"modes": {"live": {"provider": "fake"}}},  # no "model" key
    )
    result = _select_provider(state, "live")
    assert result is registered


def test_select_provider_returns_registered_when_model_matches():
    """Model override same as registered model → no clone needed."""
    registered = FakeProvider(api_key="sk-test", model="model-A")
    state = _make_state(
        providers={"fake": registered},
        cfg={"modes": {"live": {"provider": "fake", "model": "model-A"}}},
    )
    result = _select_provider(state, "live")
    assert result is registered


# ---------------------------------------------------------------------------
# 3. Does not mutate the registered instance
# ---------------------------------------------------------------------------

def test_select_provider_does_not_mutate_registered_instance():
    """Cloning for an override must not modify the shared registered provider."""
    registered = FakeProvider(api_key="sk-test", model="model-A")
    original_model = registered.model
    state = _make_state(
        providers={"fake": registered},
        cfg={"modes": {"live": {"provider": "fake", "model": "model-B"}}},
    )
    _select_provider(state, "live")
    assert registered.model == original_model, "Registered instance model was mutated!"


def test_select_provider_does_not_mutate_when_called_multiple_times():
    """Multiple calls with different mode overrides never corrupt the shared instance."""
    registered = FakeProvider(api_key="sk-test", model="model-A")
    state = _make_state(
        providers={"fake": registered},
        cfg={
            "modes": {
                "live": {"provider": "fake", "model": "model-B"},
                "brief": {"provider": "fake", "model": "model-C"},
            }
        },
    )
    live_prov = _select_provider(state, "live")
    brief_prov = _select_provider(state, "brief")

    assert live_prov.model == "model-B"
    assert brief_prov.model == "model-C"
    assert registered.model == "model-A"  # untouched


# ---------------------------------------------------------------------------
# 4. Fallback behavior (no provider in mode cfg)
# ---------------------------------------------------------------------------

def test_select_provider_falls_back_to_ollama():
    """Unrecognized provider pref → falls back to ollama."""
    from unittest.mock import MagicMock
    ollama = MagicMock()
    other = MagicMock()
    state = _make_state(
        providers={"ollama": ollama, "other": other},
        cfg={"modes": {"live": {"provider": "missing"}}},
    )
    result = _select_provider(state, "live")
    assert result is ollama


def test_select_provider_returns_none_when_no_providers():
    """Empty providers → None."""
    state = _make_state(providers={}, cfg={"modes": {"live": {"provider": "openrouter"}}})
    result = _select_provider(state, "live")
    assert result is None


def test_select_provider_skips_clone_for_provider_without_api_key():
    """Providers without api_key (e.g. OllamaProvider) skip cloning gracefully."""
    from claude_code_talker.providers.ollama import OllamaProvider
    ollama = OllamaProvider()
    state = _make_state(
        providers={"ollama": ollama},
        cfg={"modes": {"live": {"provider": "ollama", "model": "llama3.2:1b"}}},
    )
    # Should NOT crash even though OllamaProvider has no api_key
    # ollama.model IS "llama3.2:1b" by default, so no clone needed
    result = _select_provider(state, "live")
    assert result is ollama


def test_select_provider_skips_clone_for_ollama_with_different_model():
    """OllamaProvider has no api_key → clone gracefully skipped, returns original."""
    from claude_code_talker.providers.ollama import OllamaProvider
    ollama = OllamaProvider(model="llama3.2:1b")
    state = _make_state(
        providers={"ollama": ollama},
        cfg={"modes": {"live": {"provider": "ollama", "model": "qwen2.5:3b"}}},
    )
    # api_key is None → clone attempt is skipped, returns original
    result = _select_provider(state, "live")
    assert result is ollama
