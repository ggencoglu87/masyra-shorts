from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"


class TTSProvider:
    name = "base"

    def synthesize(self, text: str, output_path: Path) -> dict:
        raise NotImplementedError


class MockTTSProvider(TTSProvider):
    name = "mock"

    def __init__(self, reason: str = "Mock TTS does not create audio. voiceover.txt remains the source of truth.") -> None:
        self.reason = reason

    def synthesize(self, text: str, output_path: Path) -> dict:
        status_path = output_path.with_suffix(".mock.json")
        status_path.write_text(
            json.dumps(
                {
                    "provider": self.name,
                    "audio_created": False,
                    "warning": self.reason,
                    "text_preview": text[:240],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "provider": self.name,
            "created": False,
            "output": None,
            "warning": self.reason,
        }


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, api_key: str, voice_id: str | None = None, model_id: str | None = None) -> None:
        self.api_key = api_key
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID)
        self.model_id = model_id or os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_ELEVENLABS_MODEL_ID)

    def synthesize(self, text: str, output_path: Path) -> dict:
        payload = json.dumps(
            {
                "text": text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": 0.46,
                    "similarity_boost": 0.78,
                    "style": 0.18,
                    "use_speaker_boost": True,
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            data=payload,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            audio = response.read()

        output_path.write_bytes(audio)
        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": None,
        }


def get_tts_provider(name: str) -> TTSProvider | None:
    normalized = name.lower()
    if normalized in {"off", "none"}:
        return None
    if normalized == "mock":
        return MockTTSProvider()
    if normalized == "elevenlabs":
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return MockTTSProvider("ELEVENLABS_API_KEY is missing; no voiceover.mp3 created.")
        return ElevenLabsTTSProvider(api_key=api_key)
    raise ValueError(f"Unknown TTS provider: {name}")


def synthesize_voiceovers(video_root: Path, provider_name: str) -> dict:
    video_dirs = [
        path
        for path in sorted(video_root.iterdir())
        if path.is_dir() and (path / "voiceover.txt").exists()
    ]
    return synthesize_voiceovers_for_dirs(video_dirs, provider_name=provider_name)


def synthesize_voiceovers_for_dirs(video_dirs: list[Path], provider_name: str) -> dict:
    provider = get_tts_provider(provider_name)
    if provider is None:
        return {
            "provider": "off",
            "attempted": 0,
            "created_count": 0,
            "outputs": [],
            "warnings": [],
            "results": [],
        }

    results = []
    for video_dir in video_dirs:
        voiceover_text = video_dir / "voiceover.txt"
        output_path = video_dir / "voiceover.mp3"
        text = voiceover_text.read_text(encoding="utf-8")
        try:
            result = provider.synthesize(text=text, output_path=output_path)
        except Exception as exc:  # Network/API failures should not break package generation.
            result = {
                "provider": provider.name,
                "created": False,
                "output": None,
                "warning": f"TTS failed for {video_dir.name}: {exc}",
            }
        result["video_dir"] = str(video_dir)
        results.append(result)

    return {
        "provider": provider.name,
        "attempted": len(results),
        "created_count": sum(1 for result in results if result["created"]),
        "outputs": [result["output"] for result in results if result.get("output")],
        "warnings": [result["warning"] for result in results if result.get("warning")],
        "results": results,
    }
