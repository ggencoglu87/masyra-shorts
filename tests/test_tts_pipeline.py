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


if __name__ == "__main__":
    unittest.main()
