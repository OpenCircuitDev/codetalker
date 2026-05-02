"""TTS engine plug-in registry."""
from claude_tts.engines.base import TTSEngine
from claude_tts.engines.piper import PiperEngine

__all__ = ["TTSEngine", "PiperEngine"]
