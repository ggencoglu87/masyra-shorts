from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shorts_automation.dashboard import build_package_rows, render_package_card, render_video_detail  # noqa: E402
from shorts_automation.status_store import StatusStore  # noqa: E402


class DashboardStatusTests(unittest.TestCase):
    def test_real_clips_and_matching_tts_override_placeholder_visuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"
            video_dir = output_dir / "2026-06-12" / "videos" / "01-test"
            video_dir.mkdir(parents=True)
            (video_dir / "video-plan.json").write_text(
                json.dumps(
                    {
                        "title": "Test Short",
                        "trend": {"title": "Test trend", "category": "AI"},
                        "scores": {"viral_potential_score": 91, "trend_score": 88, "growth_score": 77},
                    }
                ),
                encoding="utf-8",
            )
            (video_dir / "final.mp4").write_bytes(b"not-a-real-mp4")
            (video_dir / "video-clips-result.json").write_text(
                json.dumps(
                    {
                        "provider": "pexels",
                        "clip_count": 8,
                        "real_clip_count": 8,
                        "publish_ready": True,
                        "clips": [{"provider": "pexels", "file": "video-clips/clip-01.mp4", "query": "viral technology"}],
                    }
                ),
                encoding="utf-8",
            )
            (video_dir / "scene-manifest.json").write_text(
                json.dumps({"scenes": [{"provider": "placeholder", "image": "scene-images/scene-01.png"}]}),
                encoding="utf-8",
            )
            (video_dir / "visual-result.json").write_text(
                json.dumps({"providers_used": ["placeholder"], "real_visuals_ready": False}),
                encoding="utf-8",
            )
            (video_dir / "tts-result.json").write_text(
                json.dumps(
                    {
                        "requested_provider": "elevenlabs",
                        "provider_used": "piper",
                        "audio_matches_current_text": True,
                        "mixed_voiceover_ready": True,
                        "estimated_duration": 30,
                        "actual_audio_duration": 30,
                    }
                ),
                encoding="utf-8",
            )
            (video_dir / "voiceover.mp3").write_bytes(b"audio")

            store = StatusStore(output_dir / "review-status.json")
            rows = build_package_rows(output_dir, store)
            card = render_package_card(output_dir, rows[0])
            detail = render_video_detail(output_dir, store, video_dir)

        self.assertTrue(rows[0]["clips_ready"])
        self.assertTrue(rows[0]["audio_ready"])
        self.assertFalse(rows[0]["publish_ready"])
        self.assertIn("Clips Ready", card)
        self.assertIn("Stock Fallback Used", card)
        self.assertIn("Voiceover Ready", card)
        self.assertIn("Actual provider used: piper", detail)
        self.assertIn("clip_count", detail)
        self.assertIn("real_clip_count", detail)
        self.assertIn("publish_ready", detail)
        self.assertIn("final.mp4", detail)
        self.assertIn("&v=", detail)
        self.assertNotIn("Placeholder visuals only", detail)


if __name__ == "__main__":
    unittest.main()
