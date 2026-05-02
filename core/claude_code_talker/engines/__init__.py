"""TTS engine plug-in registry."""
from claude_code_talker.engines.base import TTSEngine
from claude_code_talker.engines.piper import PiperEngine
from claude_code_talker.engines.edge import EdgeEngine
from claude_code_talker.engines.elevenlabs import ElevenLabsEngine

__all__ = ["TTSEngine", "PiperEngine", "EdgeEngine", "ElevenLabsEngine"]
