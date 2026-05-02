"""LLM provider plug-in registry."""
from claude_tts.providers.base import LLMProvider
from claude_tts.providers.ollama import OllamaProvider

__all__ = ["LLMProvider", "OllamaProvider"]
