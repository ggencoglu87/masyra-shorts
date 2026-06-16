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
        self.assertEqual(item["universe"]["name"], "Farm Chaos")
        self.assertEqual(len(item["storyboard"]), 4)
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

    def test_v7_story_universe_prompts_and_memory_are_episode_ready(self) -> None:
        trend = {
            "title": "Space school simulator goes wrong",
            "category": "Sports Drama",
            "sources": ["sample"],
            "youtube_views": 900_000,
            "youtube_likes": 90_000,
            "reddit_ups": 18_000,
            "youtube_search_results": 16,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "run"
            plan = build_daily_network_plan([trend], channel_name="Masyra Labs", top_n=1)
            write_video_packages(plan, output_root)
            video_dir = next((output_root / "videos").iterdir())
            storyboard = json.loads((video_dir / "storyboard.json").read_text(encoding="utf-8"))
            bible = json.loads((video_dir / "character_bible.json").read_text(encoding="utf-8"))
            library = json.loads((root / "studio" / "character-library.json").read_text(encoding="utf-8"))
            memory = json.loads((root / "studio" / "episode-memory.json").read_text(encoding="utf-8"))

        prompt = storyboard[0]["video_prompt"]
        self.assertEqual(bible["universe"]["name"], "Space Academy")
        self.assertEqual([scene["beat"] for scene in storyboard], ["Hook", "Conflict", "Escalation", "Payoff"])
        self.assertIn("Environment:", prompt)
        self.assertIn("Emotional state:", prompt)
        self.assertIn("Camera direction:", prompt)
        self.assertIn("Minimax video", prompt)
        self.assertIn("personality", prompt)
        self.assertIn("nova_cadet", library["characters"])
        self.assertIn("relationships", library["characters"]["nova_cadet"])
        self.assertTrue(library["characters"]["nova_cadet"]["history"])
        self.assertEqual(memory["episodes"][0]["universe"], "space_academy")
        self.assertIn("payoff", memory["episodes"][0])

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
