from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_PIPER_MODEL_PATH = "/opt/masyra-shorts/models/piper/en_US-lessac-medium.onnx"


class TTSProvider:
    name = "base"

    def synthesize(self, text: str, output_path: Path) -> dict:
        raise NotImplementedError


class UnavailableTTSProvider(TTSProvider):
    name = "unavailable"

    def __init__(self, provider_name: str, warning: str) -> None:
        self.name = provider_name
        self.warning = warning

    def synthesize(self, text: str, output_path: Path) -> dict:
        return {
            "provider": self.name,
            "created": False,
            "output": None,
            "warning": self.warning,
        }


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
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=mp3_44100_128",
            data=payload,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                audio = response.read()
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"ElevenLabs API error {exc.code}: {details}") from exc

        output_path.write_bytes(audio)
        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": None,
            "voice_id": self.voice_id,
            "model_id": self.model_id,
        }


class PiperTTSProvider(TTSProvider):
    name = "piper"

    def __init__(self, model_path: str | None = None, binary: str | None = None) -> None:
        self.binary = binary or os.getenv("PIPER_BIN", "piper")
        self.model_path = Path(model_path or os.getenv("PIPER_MODEL_PATH", DEFAULT_PIPER_MODEL_PATH))

    def synthesize(self, text: str, output_path: Path) -> dict:
        piper_bin = shutil.which(self.binary) if self.binary == "piper" else self.binary
        if not piper_bin:
            return {
                "provider": self.name,
                "created": False,
                "output": None,
                "warning": "Piper binary not found. Run scripts/install-piper-ubuntu.sh or set PIPER_BIN.",
                "model_path": str(self.model_path),
            }
        if not self.model_path.exists():
            return {
                "provider": self.name,
                "created": False,
                "output": None,
                "warning": f"Piper model not found: {self.model_path}. Run scripts/install-piper-ubuntu.sh or set PIPER_MODEL_PATH.",
                "model_path": str(self.model_path),
            }
        if not shutil.which("ffmpeg"):
            return {
                "provider": self.name,
                "created": False,
                "output": None,
                "warning": "FFmpeg is required to convert Piper WAV output to voiceover.mp3.",
                "model_path": str(self.model_path),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = Path(temp_dir) / "voiceover.wav"
            piper_command = [
                str(piper_bin),
                "--model",
                str(self.model_path),
                "--output_file",
                str(wav_path),
            ]
            piper_completed = subprocess.run(
                piper_command,
                input=text,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if piper_completed.returncode != 0 or not wav_path.exists():
                return {
                    "provider": self.name,
                    "created": False,
                    "output": None,
                    "warning": f"Piper synthesis failed: {piper_completed.stderr[-1000:]}",
                    "model_path": str(self.model_path),
                }

            ffmpeg_command = [
                "ffmpeg",
                "-y",
                "-i",
                str(wav_path),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(output_path),
            ]
            ffmpeg_completed = subprocess.run(ffmpeg_command, capture_output=True, text=True, timeout=120)
            if ffmpeg_completed.returncode != 0:
                return {
                    "provider": self.name,
                    "created": False,
                    "output": None,
                    "warning": f"FFmpeg MP3 conversion failed: {ffmpeg_completed.stderr[-1000:]}",
                    "model_path": str(self.model_path),
                }

        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": None,
            "model_path": str(self.model_path),
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
            return UnavailableTTSProvider("elevenlabs", "ELEVENLABS_API_KEY is missing. ElevenLabs was not called. Set ELEVENLABS_API_KEY or use TTS_PROVIDER=piper for offline Ubuntu TTS.")
        return ElevenLabsTTSProvider(api_key=api_key)
    if normalized == "piper":
        return PiperTTSProvider()
    raise ValueError(f"Unknown TTS provider: {name}")


def synthesize_voiceover(video_dir: Path, provider_name: str, force: bool = False) -> dict:
    video_dir = video_dir.resolve()
    voiceover_text = video_dir / "voiceover.txt"
    output_path = video_dir / "voiceover.mp3"
    result_path = video_dir / "tts-result.json"

    if not voiceover_text.exists():
        result = {
            "provider": provider_name,
            "created": False,
            "output": None,
            "warning": "voiceover.txt not found; TTS was not attempted.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    if output_path.exists() and not force:
        result = {
            "provider": provider_name,
            "created": False,
            "skipped": True,
            "output": str(output_path),
            "warning": "voiceover.mp3 already exists; use --force to regenerate.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    provider = get_tts_provider(provider_name)
    if provider is None:
        result = {
            "provider": "off",
            "created": False,
            "output": None,
            "warning": "TTS_PROVIDER is off; no voiceover.mp3 created.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    text = voiceover_text.read_text(encoding="utf-8").strip()
    if not text:
        result = {
            "provider": provider.name,
            "created": False,
            "output": None,
            "warning": "voiceover.txt is empty; TTS was not attempted.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    try:
        result = provider.synthesize(text=text, output_path=output_path)
    except Exception as exc:  # Network/API failures should not break package generation.
        result = {
            "provider": provider.name,
            "created": False,
            "output": None,
            "warning": f"TTS failed for {video_dir.name}: {exc}",
        }

    return _write_tts_result(video_dir, result_path, result, force=force)


def synthesize_voiceovers(video_root: Path, provider_name: str, force: bool = False) -> dict:
    video_dirs = [
        path
        for path in sorted(video_root.iterdir())
        if path.is_dir() and (path / "voiceover.txt").exists()
    ]
    return synthesize_voiceovers_for_dirs(video_dirs, provider_name=provider_name, force=force)


def synthesize_voiceovers_for_dirs(video_dirs: list[Path], provider_name: str, force: bool = False) -> dict:
    results = [synthesize_voiceover(video_dir, provider_name=provider_name, force=force) for video_dir in video_dirs]
    return {
        "provider": provider_name,
        "attempted": len(results),
        "created_count": sum(1 for result in results if result["created"]),
        "skipped_count": sum(1 for result in results if result.get("skipped")),
        "outputs": [result["output"] for result in results if result.get("output")],
        "warnings": [result["warning"] for result in results if result.get("warning")],
        "results": results,
    }


def _write_tts_result(video_dir: Path, result_path: Path, result: dict, *, force: bool) -> dict:
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video_dir": str(video_dir),
        "force": force,
        **result,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
