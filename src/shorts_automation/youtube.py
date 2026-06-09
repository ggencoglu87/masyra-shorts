from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request


class YouTubeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch_trending_videos(self, region_code: str, max_results: int = 25) -> list[dict]:
        params = {
            "part": "snippet,contentDetails,statistics",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": str(max_results),
            "key": self.api_key,
        }
        return self._get("https://www.googleapis.com/youtube/v3/videos", params)

    def search_videos(self, query: str, max_results: int = 10) -> list[dict]:
        search_params = {
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "q": query,
            "maxResults": str(max_results),
            "key": self.api_key,
        }
        search_items = self._get("https://www.googleapis.com/youtube/v3/search", search_params)
        ids = [
            item.get("id", {}).get("videoId")
            for item in search_items
            if item.get("id", {}).get("videoId")
        ]
        if not ids:
            return []

        detail_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(ids),
            "key": self.api_key,
        }
        return self._get("https://www.googleapis.com/youtube/v3/videos", detail_params)

    def _get(self, endpoint: str, params: dict[str, str]) -> list[dict]:
        url = endpoint + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if "error" in payload:
            message = payload["error"].get("message", "YouTube API error")
            raise RuntimeError(message)

        return payload.get("items", [])


def parse_iso8601_duration(value: str) -> int:
    match = re.fullmatch(r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?", value)
    if not match:
        return 0

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
