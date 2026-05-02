"""LLM provider plug-in registry."""
from claude_code_talker.providers.base import LLMProvider
from claude_code_talker.providers.ollama import OllamaProvider

__all__ = ["LLMProvider", "OllamaProvider"]
