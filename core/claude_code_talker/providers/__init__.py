"""LLM provider plug-in registry."""
from claude_code_talker.providers.base import LLMProvider
from claude_code_talker.providers.ollama import OllamaProvider
from claude_code_talker.providers.anthropic import AnthropicProvider
from claude_code_talker.providers.openrouter import OpenRouterProvider

__all__ = ["LLMProvider", "OllamaProvider", "AnthropicProvider", "OpenRouterProvider"]
