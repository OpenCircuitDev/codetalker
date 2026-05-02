"""OpenAI TTS engine."""
from __future__ import annotations

import httpx

from claude_code_talker.engines.base import TTSEngine


class OpenAIEngine(TTSEngine):
    name = "openai"
    audio_format = "wav"  # we request WAV explicitly

    BASE_URL = "https://api.openai.com/v1"
    AVAILABLE_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def __init__(self, api_key: str, model: str = "tts-1"):
        if not api_key:
            raise ValueError("OpenAIEngine requires api_key")
        self.api_key = api_key
        self.model = model

    def list_voices(self) -> list[str]:
        return list(self.AVAILABLE_VOICES)

    def synthesize(self, text: str, voice: str, rate: float) -> bytes:
        if voice not in self.AVAILABLE_VOICES:
            raise ValueError(f"unknown voice: {voice}; available: {self.AVAILABLE_VOICES}")

        # OpenAI rate is 0.25 to 4.0 (1.0 = default)
        speed = max(0.25, min(4.0, rate))

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.BASE_URL}/audio/speech",
                    json={
                        "model": self.model,
                        "voice": voice,
                        "input": text,
                        "speed": speed,
                        "response_format": "wav",
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            raise RuntimeError(f"openai tts request failed: {exc}") from exc
