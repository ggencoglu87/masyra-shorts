from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shorts_automation.stock_videos import (  # noqa: E402
    PixabayVideoProvider,
    PexelsVideoProvider,
    StockVideoError,
    _download,
    build_clip_queries,
    generate_video_clips_for_package,
)


class StockVideoProviderTests(unittest.TestCase):
    def test_pexels_search_request_uses_videos_endpoint_and_headers(self) -> None:
        with patch.dict(os.environ, {"PEXELS_API_KEY": "pexels-key"}):
            provider = PexelsVideoProvider()
            request = provider.build_search_request("https://api.pexels.com/videos/search?query=funny&per_page=1")

        self.assertEqual(request.full_url, "https://api.pexels.com/videos/search?query=funny&per_page=1")
        self.assertEqual(request.get_header("Authorization"), "pexels-key")
        self.assertTrue(request.get_header("User-agent"))

    def test_pixabay_download_uses_user_agent_and_referer(self) -> None:
        captured: list[urllib.request.Request] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return b"mp4"

        def fake_urlopen(request: urllib.request.Request, timeout: int = 0) -> FakeResponse:
            captured.append(request)
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", fake_urlopen):
            _download(
                "https://cdn.pixabay.com/video.mp4",
                Path(tmp) / "clip.mp4",
                provider="pixabay",
                referer="https://pixabay.com/videos/example-123/",
            )

        self.assertEqual(captured[0].get_header("Referer"), "https://pixabay.com/videos/example-123/")
        self.assertTrue(captured[0].get_header("User-agent"))

    def test_pixabay_http_error_includes_url_status_and_body(self) -> None:
        body = b'{"error":"forbidden"}'
        error = urllib.error.HTTPError("https://cdn.pixabay.com/video.mp4", 403, "Forbidden", {}, io.BytesIO(body))

        with tempfile.TemporaryDirectory() as tmp, patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(StockVideoError) as raised:
                _download("https://cdn.pixabay.com/video.mp4", Path(tmp) / "clip.mp4", provider="pixabay")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.url, "https://cdn.pixabay.com/video.mp4")
        self.assertIn("forbidden", raised.exception.response_body or "")

    def test_failed_pexels_search_writes_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video_dir = Path(tmp)
            (video_dir / "video-plan.json").write_text(
                json.dumps({"trend": {"title": "Funny robot reaction", "category": "AI"}}),
                encoding="utf-8",
            )
            (video_dir / "asset-prompts.json").write_text(
                json.dumps({"scenes": [{"prompt": "people surprised by viral technology"}]}),
                encoding="utf-8",
            )
            error = urllib.error.HTTPError("https://api.pexels.com/videos/search", 403, "Forbidden", {}, io.BytesIO(b'{"error":"bad auth"}'))

            with patch.dict(os.environ, {"PEXELS_API_KEY": "pexels-key", "PIXABAY_API_KEY": ""}, clear=False):
                with patch("urllib.request.urlopen", side_effect=error):
                    result = generate_video_clips_for_package(video_dir, provider_name="pexels", debug=True)

            result_path = video_dir / "video-clips-result.json"
            saved = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(result["downloaded"], 0)
        self.assertEqual(saved["fallback"], "openai_images")
        self.assertIn("bad auth", json.dumps(saved))

    def test_clip_queries_remove_brand_noise_and_include_category_queries(self) -> None:
        queries = build_clip_queries(
            {"trend": {"title": "Masyra analysis moment sleek", "category": "Sports"}},
            {"scenes": [{"prompt": "clean short question masyra sports celebration"}]},
        )

        self.assertIn("sports celebration", queries)
        self.assertIn("people surprised", queries)
        self.assertFalse(any("masyra" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
