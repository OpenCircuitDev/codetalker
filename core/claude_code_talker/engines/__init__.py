"""TTS engine plug-in registry."""
from claude_code_talker.engines.base import TTSEngine
from claude_code_talker.engines.piper import PiperEngine

__all__ = ["TTSEngine", "PiperEngine"]
