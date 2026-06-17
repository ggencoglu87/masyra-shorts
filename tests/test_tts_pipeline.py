from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shorts_automation.cli import main  # noqa: E402
from shorts_automation.tts import synthesize_voiceover  # noqa: E402


class FakeTTSProvider:
    name = "mock"

    def synthesize(self, text: str, output_path: Path) -> dict:
        output_path.write_bytes(f"audio for: {text}".encode("utf-8"))
        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": None,
        }


class FailingElevenLabsProvider:
    name = "elevenlabs"

    def synthesize(self, text: str, output_path: Path) -> dict:
        raise RuntimeError("ElevenLabs API error 429: quota_exceeded")


class FakePiperProvider:
    name = "piper"

    def synthesize(self, text: str, output_path: Path) -> dict:
        output_path.write_bytes(f"piper audio for: {text}".encode("utf-8"))
        return {
            "provider": self.name,
            "created": True,
            "output": str(output_path),
            "warning": None,
        }


class TTSPipelineTests(unittest.TestCase):
    def test_generate_tts_all_uses_each_package_voiceover_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            videos_dir = Path(tmp) / "videos"
            first = videos_dir / "01-first"
            second = videos_dir / "02-second"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            (first / "voiceover.txt").write_text("First package narration only.", encoding="utf-8")
            (second / "voiceover.txt").write_text("Second package narration only.", encoding="utf-8")

            with patch("shorts_automation.tts.get_tts_provider", return_value=FakeTTSProvider()):
                exit_code = main(["generate-tts-all", str(videos_dir), "--tts-provider", "mock"])

            first_result = json.loads((first / "tts-result.json").read_text(encoding="utf-8"))
            second_result = json.loads((second / "tts-result.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertNotEqual(first_result["source_text_hash"], second_result["source_text_hash"])
        self.assertNotEqual(first_result["generated_audio_hash"], second_result["generated_audio_hash"])
        self.assertIn("First package", first_result["source_text_preview"])
        self.assertIn("Second package", second_result["source_text_preview"])
        self.assertTrue(first_result["audio_matches_current_text"])
        self.assertTrue(second_result["audio_matches_current_text"])

    def test_existing_audio_regenerates_when_voiceover_text_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = Path(tmp) / "video"
            video_dir.mkdir()
            voiceover = video_dir / "voiceover.txt"
            voiceover.write_text("Original narration.", encoding="utf-8")

            with patch("shorts_automation.tts.get_tts_provider", return_value=FakeTTSProvider()):
                first = synthesize_voiceover(video_dir, provider_name="mock")
                second = synthesize_voiceover(video_dir, provider_name="mock")
                voiceover.write_text("Updated narration.", encoding="utf-8")
                third = synthesize_voiceover(video_dir, provider_name="mock")

        self.assertTrue(first["created"])
        self.assertTrue(second["skipped"])
        self.assertNotEqual(first["source_text_hash"], third["source_text_hash"])
        self.assertNotEqual(first["generated_audio_hash"], third["generated_audio_hash"])
        self.assertTrue(third["created"])
        self.assertTrue(third["audio_matches_current_text"])

    def test_elevenlabs_quota_failure_falls_back_to_piper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = Path(tmp) / "video"
            video_dir.mkdir()
            (video_dir / "voiceover.txt").write_text("Fallback narration.", encoding="utf-8")

            with patch(
                "shorts_automation.tts.get_tts_fallback_chain",
                return_value=[FailingElevenLabsProvider(), FakePiperProvider()],
            ):
                result = synthesize_voiceover(video_dir, provider_name="elevenlabs")

        self.assertTrue(result["created"])
        self.assertEqual(result["requested_provider"], "elevenlabs")
        self.assertEqual(result["provider_used"], "piper")
        self.assertTrue(result["audio_matches_current_text"])
        self.assertEqual(result["fallback_attempts"][0]["provider"], "elevenlabs")
        self.assertEqual(result["fallback_attempts"][1]["provider"], "piper")

    def test_multi_voice_dialogue_generates_speaker_clips_and_mixed_voiceover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = Path(tmp) / "video"
            video_dir.mkdir()
            (video_dir / "voiceover.txt").write_text(
                "\n".join(
                    [
                        "NARRATOR: Bob thought nobody saw him.",
                        "BOB_CAT: I can explain.",
                        "CARL_CHICKEN: Then explain the fish on your face.",
                    ]
                ),
                encoding="utf-8",
            )
            (video_dir / "character_bible.json").write_text(
                json.dumps(
                    {
                        "narrator_voice_profile": {"voice_id": "narrator_main", "provider": "mock"},
                        "characters": [
                            {"id": "bob_cat", "voice_profile": {"voice_id": "bob_cat", "speaking_style": "dramatic"}},
                            {"id": "carl_chicken", "voice_profile": {"voice_id": "carl_chicken", "speaking_style": "sarcastic"}},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("shorts_automation.tts.get_tts_fallback_chain", return_value=[FakeTTSProvider()]):
                result = synthesize_voiceover(video_dir, provider_name="mock")
            files_exist = {
                "narrator": (video_dir / "audio" / "narrator-01.mp3").exists(),
                "bob": (video_dir / "audio" / "bob_cat-01.mp3").exists(),
                "carl": (video_dir / "audio" / "carl_chicken-01.mp3").exists(),
                "mixed": (video_dir / "voiceover.mp3").exists(),
            }

        self.assertTrue(result["created"])
        self.assertEqual(result["voice_mode"], "multi_character")
        self.assertTrue(result["narrator_ready"])
        self.assertTrue(result["character_voices_ready"])
        self.assertTrue(result["mixed_voiceover_ready"])
        self.assertEqual(result["speaker_count"], 3)
        self.assertGreaterEqual(result["dialogue_percentage"], 30)
        self.assertIn("voice_separation_mode", result)
        self.assertTrue(files_exist["narrator"])
        self.assertTrue(files_exist["bob"])
        self.assertTrue(files_exist["carl"])
        self.assertTrue(files_exist["mixed"])
        self.assertIn("bob_cat", result["voices_used"])


if __name__ == "__main__":
    unittest.main()
