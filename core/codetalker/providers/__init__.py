"""LLM provider plug-in registry."""
from codetalker.providers.base import LLMProvider
from codetalker.providers.ollama import OllamaProvider

__all__ = ["LLMProvider", "OllamaProvider"]
