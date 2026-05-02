"""TTS engine plug-in registry."""
from codetalker.engines.base import TTSEngine
from codetalker.engines.piper import PiperEngine

__all__ = ["TTSEngine", "PiperEngine"]
