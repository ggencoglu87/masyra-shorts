from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .categories import classify_category
from .youtube import YouTubeClient

USER_AGENT = "MasyraLabsTrendBot/0.1"


def collect_live_trends(region: str, limit: int) -> list[dict]:
    trends: list[dict] = []
    api_key = os.getenv("YOUTUBE_API_KEY")

    if api_key:
        youtube = YouTubeClient(api_key=api_key)
        trends.extend(_youtube_trending(youtube, region, limit))
        trends.extend(_youtube_search(youtube, limit))

    trends.extend(_google_trends(region, limit))
    trends.extend(_reddit_trends(limit))
    return merge_trends(trends)


def merge_trends(trends: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for trend in trends:
        key = _key(trend["title"])
        current = merged.setdefault(key, _base_trend(trend))
        current["sources"] = sorted(set(current["sources"] + trend.get("sources", [])))
        current["youtube_views"] += int(trend.get("youtube_views", 0))
        current["youtube_likes"] += int(trend.get("youtube_likes", 0))
        current["reddit_ups"] += int(trend.get("reddit_ups", 0))
        current["google_traffic"] += int(trend.get("google_traffic", 0))
        current["youtube_search_results"] = max(
            int(current.get("youtube_search_results", 0)),
            int(trend.get("youtube_search_results", 0)),
        )
        current["urls"].extend(url for url in trend.get("urls", []) if url not in current["urls"])
        current["evidence"].extend(item for item in trend.get("evidence", []) if item not in current["evidence"])
    return list(merged.values())


def _base_trend(trend: dict) -> dict:
    title = trend["title"]
    return {
        "title": title,
        "category": classify_category(title),
        "sources": trend.get("sources", []),
        "published_at": trend.get("published_at", datetime.now(timezone.utc).isoformat()),
        "youtube_views": int(trend.get("youtube_views", 0)),
        "youtube_likes": int(trend.get("youtube_likes", 0)),
        "reddit_ups": int(trend.get("reddit_ups", 0)),
        "google_traffic": int(trend.get("google_traffic", 0)),
        "youtube_search_results": int(trend.get("youtube_search_results", 0)),
        "urls": list(trend.get("urls", [])),
        "evidence": list(trend.get("evidence", [])),
    }


def _youtube_trending(client: YouTubeClient, region: str, limit: int) -> list[dict]:
    videos = client.fetch_trending_videos(region_code=region, max_results=min(limit, 50))
    return [_trend_from_youtube_video(video, source="youtube_trends") for video in videos]


def _youtube_search(client: YouTubeClient, limit: int) -> list[dict]:
    queries = ["viral shorts", "ai trend", "gaming trend", "celebrity news", "funny animals"]
    trends: list[dict] = []
    per_query = max(3, limit // len(queries))
    for query in queries:
        for video in client.search_videos(query=query, max_results=per_query):
            trend = _trend_from_youtube_video(video, source="youtube_search")
            trend["youtube_search_results"] = per_query
            trends.append(trend)
    return trends


def _trend_from_youtube_video(video: dict, source: str) -> dict:
    snippet = video.get("snippet", {})
    stats = video.get("statistics", {})
    video_id = video.get("id", "")
    if isinstance(video_id, dict):
        video_id = video_id.get("videoId", "")
    title = snippet.get("title", "")
    return {
        "title": title,
        "sources": [source],
        "published_at": snippet.get("publishedAt", datetime.now(timezone.utc).isoformat()),
        "youtube_views": int(stats.get("viewCount", 0) or 0),
        "youtube_likes": int(stats.get("likeCount", 0) or 0),
        "urls": [f"https://www.youtube.com/watch?v={video_id}"] if video_id else [],
        "evidence": [f"YouTube: {snippet.get('channelTitle', 'unknown channel')}"],
    }


def _google_trends(region: str, limit: int) -> list[dict]:
    geo = "US" if region.upper() == "US" else "TR"
    url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
    try:
        body = _read_url(url)
    except OSError:
        return []

    root = ET.fromstring(body)
    trends = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title", default="")
        traffic = _traffic_to_int(item.findtext("{https://trends.google.com/trends/trendingsearches/daily}approx_traffic", default="0"))
        trends.append(
            {
                "title": title,
                "sources": ["google_trends"],
                "google_traffic": traffic,
                "urls": [item.findtext("link", default="")],
                "evidence": [f"Google Trends traffic: {traffic}"],
            }
        )
    return trends


def _reddit_trends(limit: int) -> list[dict]:
    url = f"https://www.reddit.com/r/popular.json?limit={min(limit, 50)}"
    try:
        payload = json.loads(_read_url(url))
    except (OSError, json.JSONDecodeError):
        return []

    trends = []
    for child in payload.get("data", {}).get("children", []):
        data = child.get("data", {})
        title = data.get("title", "")
        trends.append(
            {
                "title": title,
                "sources": ["reddit"],
                "reddit_ups": int(data.get("ups", 0) or 0),
                "urls": [f"https://www.reddit.com{data.get('permalink', '')}"],
                "evidence": [f"Reddit r/{data.get('subreddit', 'unknown')} ups: {data.get('ups', 0)}"],
            }
        )
    return trends


def _read_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _traffic_to_int(value: str) -> int:
    cleaned = value.replace("+", "").replace(",", "").strip()
    match = re.match(r"(\d+)([KkMm]?)", cleaned)
    if not match:
        return 0
    number = int(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "m":
        return number * 1_000_000
    if suffix == "k":
        return number * 1_000
    return number


def _key(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return " ".join(words[:8])
