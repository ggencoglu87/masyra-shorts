from __future__ import annotations

from datetime import datetime, timezone
from math import log10


def score_trend(trend: dict) -> dict:
    source_strength = _clamp(
        (trend.get("youtube_views", 0) / 1_000_000 * 18)
        + (trend.get("youtube_likes", 0) / 100_000 * 10)
        + (trend.get("reddit_ups", 0) / 25_000 * 14)
        + (trend.get("google_traffic", 0) / 100_000 * 18)
        + (len(trend.get("sources", [])) * 8),
        0,
        100,
    )

    growth_score = _growth_score(trend)
    competition_score = _competition_score(trend)
    emotional_score = _emotional_category_score(trend.get("category", "Misc Viral"))

    viral_potential_score = _clamp(
        (source_strength * 0.38)
        + (growth_score * 0.27)
        + ((100 - competition_score) * 0.18)
        + (emotional_score * 0.17),
        0,
        100,
    )

    return {
        "trend_score": round(source_strength, 2),
        "growth_score": round(growth_score, 2),
        "competition_score": round(competition_score, 2),
        "viral_potential_score": round(viral_potential_score, 2),
    }


def _growth_score(trend: dict) -> float:
    published_at = trend.get("published_at")
    if published_at:
        age_hours = _age_hours(published_at)
        views = max(int(trend.get("youtube_views", 0)), 0)
        velocity = views / max(age_hours, 1)
        youtube_velocity = min(log10(max(velocity, 1)) * 16, 100)
    else:
        youtube_velocity = 0

    google_boost = min(trend.get("google_traffic", 0) / 50_000 * 35, 35)
    reddit_boost = min(trend.get("reddit_ups", 0) / 10_000 * 25, 25)
    multi_source_boost = min(len(trend.get("sources", [])) * 8, 24)
    return _clamp(youtube_velocity + google_boost + reddit_boost + multi_source_boost, 0, 100)


def _competition_score(trend: dict) -> float:
    exact_matches = trend.get("youtube_search_results", 0)
    source_count = len(trend.get("sources", []))
    title_length_penalty = max(len(trend.get("title", "")) - 70, 0) * 0.4
    return _clamp((exact_matches * 1.7) + (source_count * 12) + title_length_penalty, 0, 100)


def _emotional_category_score(category: str) -> float:
    scores = {
        "Sports": 76,
        "Horror Stories": 88,
        "Funny Kids": 82,
        "Viral News": 74,
        "Gaming": 78,
        "AI": 80,
        "Celebrity": 77,
        "Animals": 84,
        "Movies & TV": 72,
        "Misc Viral": 68,
    }
    return scores.get(category, 68)


def _age_hours(value: str) -> float:
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 48
    return max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 1)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
