"""ElevenLabs TTS engine (paid; voice cloning support)."""
from __future__ import annotations

import httpx

from claude_code_talker.engines.base import TTSEngine


class ElevenLabsEngine(TTSEngine):
    name = "elevenlabs"
    audio_format = "mp3"

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str, model_id: str = "eleven_turbo_v2",
                 stability: float = 0.5, similarity_boost: float = 0.75):
        if not api_key:
            raise ValueError("ElevenLabsEngine requires api_key")
        self.api_key = api_key
        self.model_id = model_id
        self.stability = stability
        self.similarity_boost = similarity_boost

    def list_voices(self) -> list[str]:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self.BASE_URL}/voices",
                    headers={"xi-api-key": self.api_key},
                )
                resp.raise_for_status()
            data = resp.json()
            return [v["voice_id"] for v in data.get("voices", [])]
        except Exception:
            return []

    def synthesize(self, text: str, voice: str, rate: float) -> bytes:
        if not voice:
            raise ValueError("voice (voice_id) is required for ElevenLabs")
        # Note: ElevenLabs doesn't expose rate directly. The rate param is ignored.
        url = f"{self.BASE_URL}/text-to-speech/{voice}"
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
            },
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={
                        "xi-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            raise RuntimeError(f"elevenlabs request failed: {exc}") from exc
