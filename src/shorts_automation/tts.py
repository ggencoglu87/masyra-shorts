from __future__ import annotations

import json
import os
import hashlib
import shutil
import subprocess
import tempfile
import time
import base64
import urllib.error
import urllib.request
import wave
import re
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_PIPER_MODEL_PATH = "/opt/masyra-shorts/models/piper/en_US-lessac-medium.onnx"
DEFAULT_GOOGLE_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_GOOGLE_TTS_VOICE = "Puck"
MIN_AUDIO_DURATION_SECONDS = 25.0
MAX_AUDIO_DURATION_SECONDS = 35.0
TARGET_AUDIO_DURATION_SECONDS = 30.0
PROVIDER_WORDS_PER_SECOND = {
    "piper": 3.05,
    "google_ai_studio": 3.25,
    "google": 3.25,
    "elevenlabs": 3.15,
    "mock": 4.2,
}


class TTSProvider:
    name = "base"

    def synthesize(self, text: str, output_path: Path) -> dict:
        raise NotImplementedError

    def synthesize_voice(self, text: str, output_path: Path, voice_profile: dict) -> dict:
        return self.synthesize(text, output_path)


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

    def __init__(self, reason: str = "Mock TTS created placeholder silent audio. Configure ElevenLabs or Piper for production voice.") -> None:
        self.reason = reason

    def synthesize(self, text: str, output_path: Path) -> dict:
        _write_mock_audio(output_path, text, seed_text=text)
        status_path = output_path.with_suffix(".mock.json")
        status_path.write_text(
            json.dumps(
                {
                    "provider": self.name,
                    "audio_created": True,
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
            "created": True,
            "output": str(output_path),
            "warning": self.reason,
        }

    def synthesize_voice(self, text: str, output_path: Path, voice_profile: dict) -> dict:
        voice_seed = f"{voice_profile.get('voice_id') or output_path.stem}: {voice_profile.get('speaking_style', '')}: {text}"
        _write_mock_audio(output_path, text, seed_text=voice_seed)
        result = {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": self.reason,
        }
        result["voice_id"] = voice_profile.get("voice_id")
        result["voice_separation"] = "mock_voice_seed"
        return result


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

    def synthesize_voice(self, text: str, output_path: Path, voice_profile: dict) -> dict:
        voice_id = voice_profile.get("elevenlabs_voice_id") or self.voice_id
        provider = ElevenLabsTTSProvider(api_key=self.api_key, voice_id=voice_id, model_id=self.model_id)
        result = provider.synthesize(text, output_path)
        result["voice_profile"] = voice_profile
        result["voice_separation"] = "provider_voice_id"
        return result


class GoogleAITTSProvider(TTSProvider):
    name = "google_ai_studio"

    def __init__(self, api_key: str, model_id: str | None = None, voice_name: str | None = None) -> None:
        self.api_key = api_key
        self.model_id = model_id or os.getenv("GOOGLE_TTS_MODEL", DEFAULT_GOOGLE_TTS_MODEL)
        self.voice_name = voice_name or os.getenv("GOOGLE_TTS_VOICE", DEFAULT_GOOGLE_TTS_VOICE)

    def synthesize(self, text: str, output_path: Path) -> dict:
        payload = json.dumps(
            {
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self.voice_name,
                            }
                        }
                    },
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:generateContent?key={self.api_key}",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Google AI Studio TTS error {exc.code}: {details}") from exc

        audio = _extract_inline_audio(body)
        if not audio:
            raise RuntimeError("Google AI Studio TTS returned no inline audio data.")
        output_path.write_bytes(audio)
        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": None,
            "model_id": self.model_id,
            "voice_name": self.voice_name,
        }

    def synthesize_voice(self, text: str, output_path: Path, voice_profile: dict) -> dict:
        voice_name = voice_profile.get("google_voice_name") or self.voice_name
        provider = GoogleAITTSProvider(api_key=self.api_key, model_id=self.model_id, voice_name=voice_name)
        result = provider.synthesize(text, output_path)
        result["voice_profile"] = voice_profile
        result["voice_separation"] = "provider_voice_name"
        return result


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

    def synthesize_voice(self, text: str, output_path: Path, voice_profile: dict) -> dict:
        voice_id = _safe_filename(str(voice_profile.get("voice_id") or output_path.stem)).upper()
        model_env = voice_profile.get("piper_model_env") or f"PIPER_MODEL_PATH_{voice_id}"
        model_override = os.getenv(str(model_env))
        provider = PiperTTSProvider(model_path=model_override or str(self.model_path), binary=self.binary)
        result = provider.synthesize(text, output_path)
        result["voice_profile"] = voice_profile
        result["voice_separation"] = "piper_voice_model" if model_override else "piper_shared_model_voice_profile"
        return result


def get_tts_provider(name: str) -> TTSProvider | None:
    normalized = name.lower()
    if normalized in {"off", "none"}:
        return None
    if normalized == "mock":
        return MockTTSProvider()
    if normalized in {"google", "google_ai", "google_ai_studio"}:
        api_key = os.getenv("GOOGLE_AI_API_KEY")
        if not api_key:
            return UnavailableTTSProvider("google_ai_studio", "GOOGLE_AI_API_KEY is missing. Google AI Studio TTS was not called.")
        return GoogleAITTSProvider(api_key=api_key)
    if normalized == "elevenlabs":
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return UnavailableTTSProvider("elevenlabs", "ELEVENLABS_API_KEY is missing. ElevenLabs was not called. Set ELEVENLABS_API_KEY or use TTS_PROVIDER=piper for offline Ubuntu TTS.")
        return ElevenLabsTTSProvider(api_key=api_key)
    if normalized == "piper":
        return PiperTTSProvider()
    raise ValueError(f"Unknown TTS provider: {name}")


def get_tts_fallback_chain(name: str) -> list[TTSProvider]:
    normalized = (name or "google_ai_studio").lower()
    if normalized in {"off", "none"}:
        return []
    if normalized in {"auto", "google", "google_ai", "google_ai_studio"}:
        return [get_tts_provider("google_ai_studio"), get_tts_provider("elevenlabs"), PiperTTSProvider(), MockTTSProvider()]  # type: ignore[list-item]
    if normalized == "elevenlabs":
        return [get_tts_provider("elevenlabs"), PiperTTSProvider(), MockTTSProvider()]  # type: ignore[list-item]
    if normalized == "piper":
        return [PiperTTSProvider(), MockTTSProvider()]
    if normalized == "mock":
        return [MockTTSProvider()]
    return [get_tts_provider(normalized), PiperTTSProvider(), MockTTSProvider()]  # type: ignore[list-item]


def synthesize_voiceover(video_dir: Path, provider_name: str, force: bool = False) -> dict:
    video_dir = video_dir.resolve()
    voiceover_text = video_dir / "voiceover.txt"
    output_path = video_dir / "voiceover.mp3"
    result_path = video_dir / "tts-result.json"

    if not voiceover_text.exists():
        result = {
            "requested_provider": provider_name,
            "provider": provider_name,
            "provider_used": None,
            "created": False,
            "output": None,
            "source_text_hash": None,
            "generated_audio_hash": _file_hash(output_path),
            "audio_matches_current_text": False,
            "warning": "voiceover.txt not found; TTS was not attempted.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    text = voiceover_text.read_text(encoding="utf-8").strip()
    voice_profile = _read_json(video_dir / "voice_profile.json")
    dialogue_lines = _parse_dialogue_script(text)
    calibration = {}
    if dialogue_lines:
        dialogue_lines, calibration = _calibrate_dialogue_lines(dialogue_lines, provider_name)
        calibrated_text = _format_dialogue_script(dialogue_lines)
        if calibrated_text != text:
            voiceover_text.write_text(calibrated_text, encoding="utf-8")
            text = calibrated_text
            _write_dialogue_captions(video_dir, dialogue_lines, float(calibration.get("estimated_duration") or TARGET_AUDIO_DURATION_SECONDS))
    else:
        text, calibration = _calibrate_plain_text(text, provider_name)
        voiceover_text.write_text(text, encoding="utf-8")
    source_text_hash = _text_hash(text)
    previous = _read_json(result_path)
    previous_hash = previous.get("source_text_hash")
    previous_audio_hash = previous.get("generated_audio_hash")
    audio_hash = _file_hash(output_path)

    if output_path.exists() and not force and previous_hash == source_text_hash and previous_audio_hash == audio_hash:
        result = {
            "requested_provider": previous.get("requested_provider", provider_name),
            "provider": previous.get("provider_used") or previous.get("provider", provider_name),
            "provider_used": previous.get("provider_used") or previous.get("provider", provider_name),
            "created": False,
            "skipped": True,
            "output": str(output_path),
            "source_text_hash": source_text_hash,
            "generated_audio_hash": audio_hash,
            "audio_matches_current_text": True,
            "warning": "voiceover.mp3 already matches current voiceover.txt; use --force to regenerate.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    stale_audio_warning = None
    if output_path.exists() and not force and (previous_hash != source_text_hash or previous_audio_hash != audio_hash):
        stale_audio_warning = "voiceover.txt or voiceover.mp3 changed since TTS was created; regenerating audio."

    providers = [provider for provider in get_tts_fallback_chain(provider_name) if provider is not None]
    if not providers:
        result = {
            "requested_provider": provider_name,
            "provider": "off",
            "provider_used": None,
            "created": False,
            "output": None,
            "source_text_hash": source_text_hash,
            "generated_audio_hash": audio_hash,
            "audio_matches_current_text": output_path.exists() and previous_hash == source_text_hash,
            "warning": "TTS_PROVIDER is off; no voiceover.mp3 created.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    if not text:
        result = {
            "requested_provider": provider_name,
            "provider": providers[0].name,
            "provider_used": None,
            "created": False,
            "output": None,
            "source_text_hash": source_text_hash,
            "generated_audio_hash": audio_hash,
            "audio_matches_current_text": False,
            "warning": "voiceover.txt is empty; TTS was not attempted.",
        }
        return _write_tts_result(video_dir, result_path, result, force=force)

    if dialogue_lines:
        return _synthesize_multi_voiceover(
            video_dir=video_dir,
            provider_name=provider_name,
            providers=providers,
            dialogue_lines=dialogue_lines,
            output_path=output_path,
            result_path=result_path,
            source_text_hash=source_text_hash,
            stale_audio_warning=stale_audio_warning,
            force=force,
            calibration=calibration,
            actual_calibration_attempted=False,
        )

    attempts = []
    result = {
        "requested_provider": provider_name,
        "provider": providers[0].name,
        "provider_used": None,
        "created": False,
        "output": None,
        "warning": "No TTS provider created audio.",
    }
    for provider in providers:
        started = time.monotonic()
        try:
            attempt = provider.synthesize(text=text, output_path=output_path)
        except Exception as exc:  # Network/API failures should not break package generation.
            elapsed = round(time.monotonic() - started, 3)
            warning = f"TTS failed for {video_dir.name} with {provider.name}: {exc}"
            attempts.append({"provider": provider.name, "created": False, "warning": warning, "generation_time": elapsed})
            if provider.name == "elevenlabs" and not _should_fallback_from_elevenlabs(exc):
                continue
            continue
        elapsed = round(time.monotonic() - started, 3)
        attempt["generation_time"] = elapsed

        attempts.append(
            {
                "provider": provider.name,
                "created": bool(attempt.get("created")),
                "warning": attempt.get("warning"),
                "generation_time": elapsed,
            }
        )
        if attempt.get("created") and output_path.exists():
            result = {
                **attempt,
                "requested_provider": provider_name,
                "provider": provider.name,
                "provider_used": provider.name,
                "generation_time": elapsed,
                "voice_profile": voice_profile,
                "fallback_attempts": attempts,
            }
            estimated_duration = _estimate_plain_text_duration(text, provider.name)
            actual_duration = _audio_duration_seconds(output_path) or estimated_duration
            result["estimated_duration"] = round(estimated_duration, 2)
            result["estimated_episode_duration"] = round(estimated_duration, 2)
            result["actual_audio_duration"] = round(actual_duration, 2)
            result["duration_target_seconds"] = TARGET_AUDIO_DURATION_SECONDS
            result["duration_range_seconds"] = [MIN_AUDIO_DURATION_SECONDS, MAX_AUDIO_DURATION_SECONDS]
            result["duration_calibration"] = calibration
            result["speech_rate_profile"] = provider.name
            break

    if not result.get("created"):
        result["fallback_attempts"] = attempts

    result = {
        "source_text_hash": source_text_hash,
        "generated_audio_hash": _file_hash(output_path),
        "audio_matches_current_text": bool(output_path.exists() and result.get("created")),
        "source_text_preview": text[:240],
        "regenerated_due_to_source_change": bool(stale_audio_warning and result.get("created")),
        **result,
    }
    if stale_audio_warning and not result.get("warning"):
        result["warning"] = stale_audio_warning
    return _write_tts_result(video_dir, result_path, result, force=force)


def synthesize_voiceovers(video_root: Path, provider_name: str, force: bool = False) -> dict:
    video_dirs = [
        path
        for path in sorted(video_root.iterdir())
        if path.is_dir() and (path / "voiceover.txt").exists()
    ]
    return synthesize_voiceovers_for_dirs(video_dirs, provider_name=provider_name, force=force)


def synthesize_voiceovers_for_dirs(video_dirs: list[Path], provider_name: str, force: bool = False) -> dict:
    results = []
    for video_dir in video_dirs:
        try:
            results.append(synthesize_voiceover(video_dir, provider_name=provider_name, force=force))
        except Exception as exc:
            results.append(
                _write_tts_result(
                    video_dir.resolve(),
                    video_dir.resolve() / "tts-result.json",
                    {
                        "requested_provider": provider_name,
                        "provider": provider_name,
                        "provider_used": None,
                        "created": False,
                        "output": None,
                        "source_text_hash": None,
                        "generated_audio_hash": None,
                        "audio_matches_current_text": False,
                        "warning": f"TTS package failed without stopping batch: {exc}",
                    },
                    force=force,
                )
            )
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


def tts_status(video_dir: Path) -> dict:
    voiceover_text = video_dir / "voiceover.txt"
    output_path = video_dir / "voiceover.mp3"
    result = _read_json(video_dir / "tts-result.json")
    current_hash = _text_hash(voiceover_text.read_text(encoding="utf-8").strip()) if voiceover_text.exists() else None
    recorded_hash = result.get("source_text_hash")
    audio_hash = _file_hash(output_path)
    recorded_audio_hash = result.get("generated_audio_hash")
    return {
        "source_text_hash": current_hash,
        "recorded_source_text_hash": recorded_hash,
        "generated_audio_hash": recorded_audio_hash or audio_hash,
        "current_audio_hash": audio_hash,
        "audio_matches_current_text": bool(output_path.exists() and current_hash and recorded_hash == current_hash and recorded_audio_hash == audio_hash),
        "requested_provider": result.get("requested_provider") or result.get("provider"),
        "provider_used": result.get("provider_used") or result.get("provider"),
        "voice_mode": result.get("voice_mode", "single"),
        "voices_used": result.get("voices_used", []),
        "narrator_ready": bool(result.get("narrator_ready")),
        "character_voices_ready": bool(result.get("character_voices_ready")),
        "mixed_voiceover_ready": bool(result.get("mixed_voiceover_ready") or output_path.exists()),
    }


def _synthesize_multi_voiceover(
    *,
    video_dir: Path,
    provider_name: str,
    providers: list[TTSProvider],
    dialogue_lines: list[dict],
    output_path: Path,
    result_path: Path,
    source_text_hash: str,
    stale_audio_warning: str | None,
    force: bool,
    calibration: dict | None = None,
    actual_calibration_attempted: bool = False,
) -> dict:
    audio_dir = video_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    character_bible = _read_json(video_dir / "character_bible.json")
    voice_profiles = _voice_profiles(character_bible)
    attempts = []
    clips = []
    speaker_counts: dict[str, int] = {}
    providers_used = []

    for line in dialogue_lines:
        speaker_id = line["speaker_id"]
        speaker_counts[speaker_id] = speaker_counts.get(speaker_id, 0) + 1
        clip_path = audio_dir / f"{_safe_filename(speaker_id)}-{speaker_counts[speaker_id]:02d}.mp3"
        voice_profile = voice_profiles.get(speaker_id, {})
        created = None
        for provider in providers:
            started = time.monotonic()
            try:
                synthesize_voice = getattr(provider, "synthesize_voice", None)
                if callable(synthesize_voice):
                    attempt = synthesize_voice(text=line["line"], output_path=clip_path, voice_profile=voice_profile)
                else:
                    attempt = provider.synthesize(text=line["line"], output_path=clip_path)
            except Exception as exc:
                elapsed = round(time.monotonic() - started, 3)
                attempts.append(
                    {
                        "speaker_id": speaker_id,
                        "provider": provider.name,
                        "created": False,
                        "warning": f"TTS failed for {speaker_id} with {provider.name}: {exc}",
                        "generation_time": elapsed,
                        "voice_profile": voice_profile,
                    }
                )
                continue
            elapsed = round(time.monotonic() - started, 3)
            attempt = {
                **attempt,
                "speaker_id": speaker_id,
                "line": line["line"],
                "emotion": line.get("emotion"),
                "generation_time": elapsed,
                "voice_profile": voice_profile,
            }
            attempts.append(attempt)
            if attempt.get("created") and clip_path.exists():
                created = attempt
                providers_used.append(provider.name)
                break
        if not created:
            result = {
                "requested_provider": provider_name,
                "provider": providers[0].name if providers else "off",
                "provider_used": None,
                "voice_mode": "multi_character",
                "created": False,
                "output": None,
                "source_text_hash": source_text_hash,
                "generated_audio_hash": _file_hash(output_path),
                "audio_matches_current_text": False,
                "narrator_ready": False,
                "character_voices_ready": False,
                "mixed_voiceover_ready": False,
                "voices_used": sorted(set(speaker_counts)),
                "clips": clips,
                "fallback_attempts": attempts,
                "warning": f"No TTS provider created audio for speaker {speaker_id}.",
            }
            return _write_tts_result(video_dir, result_path, result, force=force)
        clips.append(
            {
                "speaker_id": speaker_id,
                "line": line["line"],
                "emotion": line.get("emotion"),
                "file": clip_path.relative_to(video_dir).as_posix(),
                "provider_used": created.get("provider"),
                "voice_profile": voice_profile,
            }
        )

    mixed = _mix_audio_clips([video_dir / clip["file"] for clip in clips], output_path)
    voices_used = sorted({clip["speaker_id"] for clip in clips})
    character_voices = [voice for voice in voices_used if voice != "narrator"]
    metrics = _dialogue_metrics(video_dir, dialogue_lines)
    actual_duration = _mixed_audio_duration(video_dir, output_path, clips, providers_used[0] if providers_used else provider_name)
    if mixed and output_path.exists() and not actual_calibration_attempted and actual_duration and not _duration_in_range(actual_duration):
        adjusted_lines, actual_calibration = _calibrate_dialogue_lines(dialogue_lines, providers_used[0] if providers_used else provider_name, actual_duration=actual_duration)
        calibrated_text = _format_dialogue_script(adjusted_lines)
        (video_dir / "voiceover.txt").write_text(calibrated_text, encoding="utf-8")
        _write_dialogue_captions(video_dir, adjusted_lines, float(actual_calibration.get("estimated_duration") or TARGET_AUDIO_DURATION_SECONDS))
        return _synthesize_multi_voiceover(
            video_dir=video_dir,
            provider_name=provider_name,
            providers=providers,
            dialogue_lines=adjusted_lines,
            output_path=output_path,
            result_path=result_path,
            source_text_hash=_text_hash(calibrated_text),
            stale_audio_warning="Audio duration was outside 25-35s; narration and dialogue were automatically calibrated.",
            force=True,
            calibration=actual_calibration,
            actual_calibration_attempted=True,
        )
    separation_modes = sorted({str(attempt.get("voice_separation")) for attempt in attempts if attempt.get("voice_separation")})
    result = {
        "requested_provider": provider_name,
        "provider": providers_used[0] if providers_used else providers[0].name,
        "provider_used": ",".join(dict.fromkeys(providers_used)),
        "voice_mode": "multi_character",
        "created": bool(mixed and output_path.exists()),
        "output": str(output_path) if output_path.exists() else None,
        "source_text_hash": source_text_hash,
        "generated_audio_hash": _file_hash(output_path),
        "audio_matches_current_text": bool(mixed and output_path.exists()),
        "source_text_preview": "\n".join(f"{line['speaker_id'].upper()}: {line['line']}" for line in dialogue_lines)[:240],
        "regenerated_due_to_source_change": bool(stale_audio_warning and mixed),
        "narrator_ready": "narrator" in voices_used,
        "character_voices_ready": bool(character_voices) and all((video_dir / clip["file"]).exists() for clip in clips if clip["speaker_id"] != "narrator"),
        "mixed_voiceover_ready": bool(mixed and output_path.exists()),
        "voices_used": voices_used,
        "speaker_count": len(voices_used),
        "estimated_episode_duration": metrics["estimated_episode_duration"],
        "estimated_duration": metrics["estimated_episode_duration"],
        "actual_audio_duration": round(actual_duration, 2) if actual_duration else None,
        "duration_target_seconds": TARGET_AUDIO_DURATION_SECONDS,
        "duration_range_seconds": [MIN_AUDIO_DURATION_SECONDS, MAX_AUDIO_DURATION_SECONDS],
        "duration_calibration": calibration or {},
        "speech_rate_profile": providers_used[0] if providers_used else provider_name,
        "dialogue_percentage": metrics["dialogue_percentage"],
        "dialogue_line_count": metrics["line_count"],
        "voice_separation_mode": ", ".join(separation_modes) or "shared_provider_settings",
        "clips": clips,
        "fallback_attempts": attempts,
        "warning": None if mixed else "Dialogue clips were created, but final voiceover.mp3 mix failed.",
    }
    if stale_audio_warning and not result.get("warning"):
        result["warning"] = stale_audio_warning
    return _write_tts_result(video_dir, result_path, result, force=force)


def _parse_dialogue_script(text: str) -> list[dict]:
    lines = []
    for raw in text.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_]+)\s*:\s*(.+?)\s*$", raw)
        if match:
            lines.append({"speaker_id": match.group(1).lower(), "line": match.group(2), "emotion": "dialogue"})
    return lines if len(lines) >= 2 else []


def _voice_profiles(character_bible: dict) -> dict:
    profiles = {"narrator": character_bible.get("narrator_voice_profile", {})}
    for character in character_bible.get("characters", []):
        if character.get("id"):
            profiles[character["id"]] = character.get("voice_profile", {})
    return profiles


def _dialogue_metrics(video_dir: Path, dialogue_lines: list[dict]) -> dict:
    storyboard = _read_json(video_dir / "storyboard.json")
    timed_lines = []
    if isinstance(storyboard, list):
        for scene in storyboard:
            for line in scene.get("dialogue", []):
                if isinstance(line, dict) and line.get("line"):
                    timed_lines.append(line)
    source = timed_lines or dialogue_lines
    starts = [float(line.get("start", 0) or 0) for line in source if isinstance(line, dict)]
    ends = [float(line.get("end", 0) or 0) for line in source if isinstance(line, dict)]
    estimated_duration = max(ends) if ends else max(0.0, len(dialogue_lines) * 1.6)
    character_lines = [line for line in dialogue_lines if line.get("speaker_id") != "narrator"]
    dialogue_percentage = round((len(character_lines) / max(len(dialogue_lines), 1)) * 100, 2)
    return {
        "estimated_episode_duration": round(estimated_duration, 2),
        "dialogue_percentage": dialogue_percentage,
        "line_count": len(dialogue_lines),
    }


def _calibrate_dialogue_lines(dialogue_lines: list[dict], provider_name: str, actual_duration: float | None = None) -> tuple[list[dict], dict]:
    provider = _normalize_provider_name(provider_name)
    estimated = actual_duration or _estimate_dialogue_duration(dialogue_lines, provider)
    calibrated = [dict(line) for line in dialogue_lines]
    changed = False
    action = "none"
    if estimated > MAX_AUDIO_DURATION_SECONDS:
        calibrated = _shorten_dialogue(calibrated, TARGET_AUDIO_DURATION_SECONDS / estimated)
        changed = True
        action = "shortened"
    elif estimated < MIN_AUDIO_DURATION_SECONDS:
        calibrated = _expand_dialogue(calibrated, provider)
        changed = True
        action = "expanded"
    calibrated_estimate = _estimate_dialogue_duration(calibrated, provider)
    return calibrated, {
        "changed": changed,
        "action": action,
        "provider": provider,
        "speech_rate_words_per_second": _speech_rate(provider),
        "estimated_before": round(estimated, 2),
        "estimated_duration": round(calibrated_estimate, 2),
    }


def _shorten_dialogue(dialogue_lines: list[dict], ratio: float) -> list[dict]:
    for line in dialogue_lines:
        words = _words(line.get("line", ""))
        keep = max(2, min(len(words), int(len(words) * max(0.35, ratio))))
        line["line"] = _restore_sentence(words[:keep])
    return dialogue_lines


def _expand_dialogue(dialogue_lines: list[dict], provider_name: str) -> list[dict]:
    reactions = [
        "Nobody moved for a second.",
        "Then everything got worse.",
        "That was the moment they understood.",
        "The room went completely quiet.",
        "One tiny detail changed the whole story.",
    ]
    character_speakers = [line.get("speaker_id") for line in dialogue_lines if line.get("speaker_id") and line.get("speaker_id") != "narrator"]
    fallback_speakers = character_speakers or [line.get("speaker_id", "narrator") for line in dialogue_lines]
    index = 0
    while _estimate_dialogue_duration(dialogue_lines, provider_name) < MIN_AUDIO_DURATION_SECONDS and index < 20:
        source = dialogue_lines[index % len(dialogue_lines)]
        speaker_id = fallback_speakers[index % len(fallback_speakers)] if index % 3 else source.get("speaker_id", "narrator")
        dialogue_lines.insert(
            min(len(dialogue_lines), index + 1),
            {
                "speaker_id": speaker_id,
                "line": reactions[index % len(reactions)],
                "emotion": source.get("emotion", "surprised"),
            },
        )
        index += 1
    return dialogue_lines


def _estimate_dialogue_duration(dialogue_lines: list[dict], provider_name: str) -> float:
    return round(sum(_estimate_line_duration(line.get("line", ""), provider_name) for line in dialogue_lines), 2)


def _estimate_plain_text_duration(text: str, provider_name: str) -> float:
    return len(_words(text)) / _speech_rate(provider_name)


def _calibrate_plain_text(text: str, provider_name: str) -> tuple[str, dict]:
    provider = _normalize_provider_name(provider_name)
    estimated = _estimate_plain_text_duration(text, provider)
    changed = False
    action = "none"
    words = _words(text)
    if estimated > MAX_AUDIO_DURATION_SECONDS:
        keep = max(12, int(len(words) * (TARGET_AUDIO_DURATION_SECONDS / estimated)))
        text = _restore_sentence(words[:keep])
        changed = True
        action = "shortened"
    elif estimated < MIN_AUDIO_DURATION_SECONDS:
        expansions = [
            "Nobody understood what was happening yet.",
            "Then one small detail made the whole scene feel bigger.",
            "Everyone paused because the answer was almost there.",
            "The final clue changed everything.",
        ]
        index = 0
        while _estimate_plain_text_duration(text, provider) < MIN_AUDIO_DURATION_SECONDS and index < 20:
            text = f"{text.rstrip()} {expansions[index % len(expansions)]}"
            index += 1
        changed = True
        action = "expanded"
    calibrated_estimate = _estimate_plain_text_duration(text, provider)
    return text, {
        "changed": changed,
        "action": action,
        "provider": provider,
        "speech_rate_words_per_second": _speech_rate(provider),
        "estimated_before": round(estimated, 2),
        "estimated_duration": round(calibrated_estimate, 2),
    }


def _estimate_line_duration(text: str, provider_name: str) -> float:
    return max(0.55, len(_words(text)) / _speech_rate(provider_name) + 0.15)


def _speech_rate(provider_name: str) -> float:
    return PROVIDER_WORDS_PER_SECOND.get(_normalize_provider_name(provider_name), 3.1)


def _normalize_provider_name(provider_name: str) -> str:
    provider = (provider_name or "mock").split(",", 1)[0].lower()
    if provider in {"google", "google_ai"}:
        return "google_ai_studio"
    return provider


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text or "")


def _restore_sentence(words: list[str]) -> str:
    if not words:
        return "Wait."
    sentence = " ".join(words)
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."


def _format_dialogue_script(dialogue_lines: list[dict]) -> str:
    return "\n".join(f"{str(line.get('speaker_id', 'narrator')).upper()}: {line.get('line', '').strip()}" for line in dialogue_lines)


def _write_dialogue_captions(video_dir: Path, dialogue_lines: list[dict], duration: float) -> None:
    captions = []
    current = 0.0
    for line in dialogue_lines:
        words = _words(line.get("line", ""))
        if not words:
            continue
        line_duration = max(0.55, _estimate_line_duration(line.get("line", ""), "mock"))
        step = line_duration / max(len(words), 1)
        speaker = str(line.get("speaker_id", "narrator")).upper()
        for index, word in enumerate(words):
            captions.append(
                {
                    "speaker_id": line.get("speaker_id", "narrator"),
                    "speaker": speaker,
                    "word": word.upper(),
                    "start": round(current + (index * step), 2),
                    "end": round(current + ((index + 1) * step), 2),
                }
            )
        current += line_duration
    (video_dir / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")


def _duration_in_range(duration: float) -> bool:
    return MIN_AUDIO_DURATION_SECONDS <= duration <= MAX_AUDIO_DURATION_SECONDS


def _mixed_audio_duration(video_dir: Path, output_path: Path, clips: list[dict], provider_name: str) -> float | None:
    total = 0.0
    for clip in clips:
        clip_path = video_dir / clip["file"]
        total += _audio_duration_seconds(clip_path) or _estimate_line_duration(clip.get("line", ""), provider_name)
    duration = _audio_duration_seconds(output_path)
    if duration and (not total or duration >= total * 0.8):
        return duration
    return round(total, 2) if total else None


def _audio_duration_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            if rate:
                return round(frames / float(rate), 2)
    except (wave.Error, OSError):
        pass
    if shutil.which("ffprobe"):
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode == 0:
            try:
                return round(float(completed.stdout.strip()), 2)
            except ValueError:
                return None
    return None


def _mix_audio_clips(clips: list[Path], output_path: Path) -> bool:
    clips = [clip for clip in clips if clip.exists()]
    if not clips:
        return False
    if shutil.which("ffmpeg"):
        command = ["ffmpeg", "-y"]
        for clip in clips:
            command.extend(["-i", str(clip)])
        command.extend(
            [
                "-filter_complex",
                "".join(f"[{index}:a]" for index in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1[a]",
                "-map",
                "[a]",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(output_path),
            ]
        )
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if completed.returncode == 0 and output_path.exists():
            return True
    with output_path.open("wb") as mixed:
        for clip in clips:
            mixed.write(clip.read_bytes())
    return output_path.exists()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "voice"


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _should_fallback_from_elevenlabs(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in ["quota_exceeded", "billing", "401", "429"])


def _extract_inline_audio(response: dict) -> bytes | None:
    candidates = response.get("candidates", [])
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts", [])
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                return base64.b64decode(inline["data"])
    return None


def _write_mock_audio(output_path: Path, text: str, seed_text: str | None = None) -> None:
    seed = hashlib.sha256((seed_text or text).encode("utf-8")).digest()
    duration = min(35.0, max(0.55, _estimate_line_duration(text, "mock")))
    frame_count = max(1, int(16000 * duration))
    frames = bytearray()
    for index in range(frame_count):
        byte = seed[index % len(seed)]
        sample = (byte - 128) * 6
        frames.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
    if shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = Path(temp_dir) / "mock.wav"
            _write_wav(wav_path, bytes(frames))
            completed = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "128k", str(output_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if completed.returncode == 0 and output_path.exists():
                return
    # Fallback: WAV content is written to the requested path so local smoke tests
    # can still run without FFmpeg.
    _write_wav(output_path, bytes(frames))


def _write_wav(output_path: Path, frames: bytes) -> None:
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(frames)
