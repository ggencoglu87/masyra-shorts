from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shorts_automation.ai_video import generate_ai_videos_for_package  # noqa: E402
from shorts_automation.dashboard import build_package_rows  # noqa: E402
from shorts_automation.planner import build_daily_network_plan, write_video_packages  # noqa: E402
from shorts_automation.quality import score_video_package  # noqa: E402
from shorts_automation.renderer import render_video_package  # noqa: E402
from shorts_automation.status_store import StatusStore  # noqa: E402


class FakeHTTPResponse:
    def __init__(self, payload: dict | bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class AIMovieEngineV4Tests(unittest.TestCase):
    def _package(self, root: Path, category: str = "Funny Animals") -> Path:
        plan = build_daily_network_plan(
            [
                {
                    "title": "Cat blamed for stealing fish",
                    "category": category,
                    "youtube_views": 2_000_000,
                    "youtube_likes": 200_000,
                    "reddit_ups": 40_000,
                    "youtube_search_results": 12,
                    "sources": ["sample"],
                }
            ],
            channel_name="Masyra Labs",
            top_n=1,
        )
        write_video_packages(plan, root)
        return next((root / "videos").iterdir())

    def test_character_bible_generation_creates_consistent_character_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            bible = json.loads((video_dir / "character_bible.json").read_text(encoding="utf-8"))

        ids = [character["id"] for character in bible["characters"]]
        self.assertEqual(ids, ["bob_cat", "carl_chicken"])
        self.assertTrue(all(character.get("appearance_hash") for character in bible["characters"]))

    def test_storyboard_prompts_include_exact_character_appearance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            storyboard = json.loads((video_dir / "storyboard.json").read_text(encoding="utf-8"))

        prompt = storyboard[0]["image_prompt"]
        self.assertIn("orange tabby cat, green eyes, red baseball cap", prompt)
        self.assertIn("white chicken, blue scarf", prompt)
        self.assertIn("bob_cat", storyboard[0]["characters"])

    def test_forbidden_phrases_never_appear_in_script(self) -> None:
        forbidden = [
            "This trend is moving fast",
            "People are talking about",
            "Everyone is talking about",
            "Viral trend",
            "Masyra Labs take",
            "Generic trend",
            "Watch this trend",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            script = (video_dir / "script.txt").read_text(encoding="utf-8")

        for phrase in forbidden:
            self.assertNotIn(phrase, script)

    def test_renderer_prioritizes_scene_videos_over_stock_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            (video_dir / "scene-videos").mkdir()
            for index in range(1, 5):
                (video_dir / "scene-videos" / f"scene-{index:02d}.mp4").write_bytes(b"ai")
            (video_dir / "ai-video-result.json").write_text(
                json.dumps({"generated_count": 4, "scenes": [{"file": f"scene-videos/scene-{index:02d}.mp4"} for index in range(1, 5)]}),
                encoding="utf-8",
            )
            with patch("shorts_automation.renderer.ffmpeg_available", return_value=True):
                with patch("shorts_automation.renderer._render_ai_scene_video", return_value={"rendered": True, "output": "ai", "ai_scene_videos_used": True}) as ai_render:
                    with patch("shorts_automation.renderer._render_clip_video") as stock_render:
                        result = render_video_package(video_dir)

        self.assertTrue(result["ai_scene_videos_used"])
        ai_render.assert_called_once()
        stock_render.assert_not_called()

    def test_dashboard_status_detects_ai_videos_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            video_dir = self._package(output_dir / "2026-06-12")
            (video_dir / "final.mp4").write_bytes(b"mp4")
            (video_dir / "ai-video-result.json").write_text(
                json.dumps(
                    {
                        "provider": "veo",
                        "scene_count": 5,
                        "generated_count": 5,
                        "character_consistency_score": 90,
                        "visual_quality_score": 88,
                        "motion_quality_score": 84,
                        "ai_movie_ready": True,
                    }
                ),
                encoding="utf-8",
            )
            rows = build_package_rows(output_dir, StatusStore(output_dir / "review-status.json"))

        self.assertTrue(rows[0]["asset_status"]["ai_videos_ready"])
        self.assertEqual(rows[0]["asset_status"]["ai_video_provider"], "veo")

    def test_ai_video_provider_off_marks_not_ai_movie_ready_without_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            result = generate_ai_videos_for_package(video_dir, provider_name="off")

        self.assertEqual(result["provider"], "off")
        self.assertFalse(result["ai_movie_ready"])
        self.assertEqual(result["generated_count"], 0)

    def test_replicate_provider_generates_scene_videos_from_scene_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            image_dir = video_dir / "scene-images"
            image_dir.mkdir()
            for index in range(1, 6):
                (image_dir / f"scene-{index:02d}.png").write_bytes(b"fake-png")

            requests = []

            def fake_urlopen(request, timeout=120):
                requests.append(request)
                url = request.full_url
                if url.endswith("/v1/predictions"):
                    return FakeHTTPResponse(
                        {
                            "id": f"pred-{len(requests)}",
                            "status": "processing",
                            "urls": {"get": "https://api.replicate.com/v1/predictions/pred"},
                        }
                    )
                if "/v1/predictions/pred" in url:
                    return FakeHTTPResponse(
                        {
                            "id": "pred",
                            "status": "succeeded",
                            "output": "https://replicate.delivery/output.mp4",
                            "metrics": {"predict_time": 1.25},
                        }
                    )
                if url == "https://replicate.delivery/output.mp4":
                    return FakeHTTPResponse(b"mp4")
                raise AssertionError(f"Unexpected URL: {url}")

            with patch.dict(
                "os.environ",
                {"REPLICATE_API_TOKEN": "r8_test", "REPLICATE_VIDEO_MODEL": "owner/video-model", "REPLICATE_POLL_INTERVAL_SECONDS": "0"},
            ):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    result = generate_ai_videos_for_package(video_dir, provider_name="replicate", force=True)

            self.assertEqual(result["provider"], "replicate")
            self.assertEqual(result["generated_count"], 5)
            self.assertEqual(result["failed_count"], 0)
            self.assertTrue(result["ai_movie_ready"])
            self.assertTrue((video_dir / "scene-videos" / "scene-01.mp4").exists())
            self.assertEqual((video_dir / "scene-videos" / "scene-01.mp4").read_bytes(), b"mp4")
            first_create_request = requests[0]
            self.assertEqual(first_create_request.headers["Authorization"], "Bearer r8_test")
            payload = json.loads(first_create_request.data.decode("utf-8"))
            self.assertEqual(payload["version"], "owner/video-model")
            self.assertIn("prompt", payload["input"])
            self.assertIn("negative_prompt", payload["input"])
            self.assertEqual(payload["input"]["aspect_ratio"], "9:16")
            self.assertTrue(payload["input"]["image"].startswith("data:image/png;base64,"))
            self.assertEqual(result["scenes"][0]["provider_response"]["status"], "succeeded")

    def test_replicate_provider_supports_text_to_video_when_scene_image_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            requests = []

            def fake_urlopen(request, timeout=120):
                requests.append(request)
                if request.full_url.endswith("/v1/predictions"):
                    return FakeHTTPResponse({"id": "pred", "status": "succeeded", "output": "https://replicate.delivery/output.mp4"})
                return FakeHTTPResponse(b"mp4")

            with patch.dict(
                "os.environ",
                {"REPLICATE_API_TOKEN": "r8_test", "REPLICATE_VIDEO_MODEL": "owner/video-model", "REPLICATE_POLL_INTERVAL_SECONDS": "0"},
            ):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    generate_ai_videos_for_package(video_dir, provider_name="replicate", force=True)

        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertNotIn("image", payload["input"])

    def test_v5_auto_provider_chain_falls_back_and_writes_provider_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            image_dir = video_dir / "scene-images"
            image_dir.mkdir()
            for index in range(1, 6):
                (image_dir / f"scene-{index:02d}.png").write_bytes(b"fake-png")

            def fake_urlopen(request, timeout=120):
                if request.full_url.endswith("/v1/predictions"):
                    return FakeHTTPResponse({"id": "pred", "status": "succeeded", "output": "https://replicate.delivery/output.mp4"})
                return FakeHTTPResponse(b"mp4")

            with patch.dict(
                "os.environ",
                {
                    "AI_VIDEO_PROVIDER_PRIORITY": "veo3,runway,replicate",
                    "GOOGLE_AI_API_KEY": "google-key",
                    "RUNWAY_API_KEY": "runway-key",
                    "REPLICATE_API_TOKEN": "r8_test",
                    "REPLICATE_VIDEO_MODEL": "owner/video-model",
                    "REPLICATE_POLL_INTERVAL_SECONDS": "0",
                },
            ):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    result = generate_ai_videos_for_package(video_dir, provider_name="auto", force=True)

            status = json.loads((video_dir / "providers-status.json").read_text(encoding="utf-8"))

        self.assertEqual(result["provider_priority"][:3], ["veo3", "runway", "replicate"])
        self.assertTrue(result["ai_movie_ready"])
        self.assertEqual(result["generated_count"], 5)
        first_scene_chain = [attempt["provider"] for attempt in result["scenes"][0]["fallback_chain"]]
        self.assertEqual(first_scene_chain, ["veo3", "runway", "replicate"])
        self.assertEqual(status["providers"]["veo3"]["failure_count"], 5)
        self.assertEqual(status["providers"]["runway"]["failure_count"], 5)
        self.assertEqual(status["providers"]["replicate"]["success_count"], 5)

    def test_quality_rejects_stock_only_as_full_ai_movie(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = self._package(Path(tmp))
            (video_dir / "final.mp4").write_bytes(b"mp4")
            (video_dir / "voiceover.mp3").write_bytes(b"audio")
            (video_dir / "video-clips-result.json").write_text(
                json.dumps({"real_clip_count": 4, "publish_ready": True, "clips": []}),
                encoding="utf-8",
            )
            result = score_video_package(video_dir)

        self.assertFalse(result["ai_movie_ready"])
        self.assertFalse(result["requirements"]["ai_scene_videos"])


if __name__ == "__main__":
    unittest.main()
