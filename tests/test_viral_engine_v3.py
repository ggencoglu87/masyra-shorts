from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shorts_automation.planner import build_daily_network_plan, write_video_packages  # noqa: E402
from shorts_automation.scoring import score_trend  # noqa: E402


class ViralEngineV3Tests(unittest.TestCase):
    def test_story_package_replaces_generic_trend_template(self) -> None:
        trend = {
            "title": "Cat knocks cup over and blames dog",
            "category": "Funny Animals",
            "sources": ["youtube_trends"],
            "youtube_views": 2_000_000,
            "youtube_likes": 150_000,
            "reddit_ups": 20_000,
            "youtube_search_results": 12,
        }
        plan = build_daily_network_plan([trend], channel_name="Masyra Labs", top_n=1)
        item = plan["items"][0]

        self.assertEqual(item["trend"]["category"], "Funny Animals")
        self.assertEqual(item["channel_target"], "animals")
        self.assertIn("hook_score", item["scores"])
        self.assertIn("shareability_score", item["scores"])
        self.assertIn("completion_probability", item["scores"])
        self.assertNotIn("This trend is moving fast", item["narration"])
        self.assertEqual(len(item["storyboard"]), 5)
        self.assertEqual(item["storyboard"][0]["beat"], "Hook")
        self.assertIn("cat reaction", json.dumps(item["storyboard"]))

    def test_written_package_contains_storyboard_captions_and_voice_profile(self) -> None:
        trend = {
            "title": "Door camera catches knocking with nobody outside",
            "category": "Horror Stories",
            "sources": ["reddit"],
            "youtube_views": 800_000,
            "youtube_likes": 70_000,
            "reddit_ups": 35_000,
            "youtube_search_results": 20,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = build_daily_network_plan([trend], channel_name="Masyra Labs", top_n=1)
            write_video_packages(plan, root)
            video_dir = next((root / "videos").iterdir())
            storyboard = json.loads((video_dir / "storyboard.json").read_text(encoding="utf-8"))
            captions = json.loads((video_dir / "captions.json").read_text(encoding="utf-8"))
            video_plan = json.loads((video_dir / "video-plan.json").read_text(encoding="utf-8"))

        self.assertEqual(storyboard[0]["time"], "0-3s")
        self.assertTrue(captions[0]["word"].isupper())
        self.assertEqual(video_plan["voice_profile"]["style"], "slow and suspenseful")
        self.assertEqual(video_plan["channel_target"], "horror")

    def test_scoring_exposes_v3_viral_metrics(self) -> None:
        scores = score_trend(
            {
                "title": "Team down by 30 makes impossible comeback",
                "category": "Sports Drama",
                "youtube_views": 1_500_000,
                "youtube_likes": 110_000,
                "reddit_ups": 40_000,
                "youtube_search_results": 25,
            }
        )

        for key in [
            "hook_score",
            "curiosity_score",
            "payoff_score",
            "shareability_score",
            "completion_probability",
            "rewatch_probability",
            "viral_score",
            "publish_ready",
        ]:
            self.assertIn(key, scores)


if __name__ == "__main__":
    unittest.main()
