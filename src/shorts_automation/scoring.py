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
    momentum_score = _clamp((growth_score * 0.62) + (source_strength * 0.28) + (emotional_score * 0.10), 0, 100)
    hook_score = _hook_score(trend)
    curiosity_score = _curiosity_score(trend)
    payoff_score = _payoff_score(trend)
    shareability_score = _shareability_score(trend, emotional_score)
    completion_probability = _clamp((hook_score * 0.30) + (curiosity_score * 0.24) + (payoff_score * 0.24) + (emotional_score * 0.22), 0, 100)
    rewatch_probability = _clamp((payoff_score * 0.42) + (shareability_score * 0.34) + (hook_score * 0.24), 0, 100)

    viral_potential_score = _clamp(
        (source_strength * 0.38)
        + (growth_score * 0.27)
        + ((100 - competition_score) * 0.18)
        + (emotional_score * 0.17),
        0,
        100,
    )
    viral_score = _clamp(
        (hook_score * 0.20)
        + (curiosity_score * 0.18)
        + (payoff_score * 0.18)
        + (shareability_score * 0.18)
        + (completion_probability * 0.16)
        + (rewatch_probability * 0.10),
        0,
        100,
    )

    return {
        "trend_score": round(source_strength, 2),
        "growth_score": round(growth_score, 2),
        "competition_score": round(competition_score, 2),
        "momentum_score": round(momentum_score, 2),
        "viral_potential_score": round(viral_potential_score, 2),
        "hook_score": round(hook_score, 2),
        "curiosity_score": round(curiosity_score, 2),
        "payoff_score": round(payoff_score, 2),
        "shareability_score": round(shareability_score, 2),
        "completion_probability": round(completion_probability, 2),
        "rewatch_probability": round(rewatch_probability, 2),
        "viral_score": round(viral_score, 2),
        "publish_ready": viral_score >= 72 and completion_probability >= 70,
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
        "Funny Animals": 92,
        "Funny Kids": 88,
        "Funny Fails": 90,
        "Horror Stories": 88,
        "Reddit Stories": 84,
        "Sports Drama": 86,
        "Relationship Stories": 89,
        "Minecraft Stories": 83,
        "Motivational Stories": 82,
        "Celebrity Drama": 86,
        "Survival Stories": 90,
        "Crazy Facts": 85,
    }
    return scores.get(category, 78)


def _hook_score(trend: dict) -> float:
    title = trend.get("title", "").lower()
    category = trend.get("category", "")
    trigger = 14 if any(word in title for word in ["shocks", "mistake", "secret", "caught", "fails", "unexpected", "viral"]) else 0
    category_boost = _emotional_category_score(category) * 0.55
    return _clamp(38 + category_boost + trigger, 0, 100)


def _curiosity_score(trend: dict) -> float:
    title = trend.get("title", "").lower()
    mystery = 18 if any(word in title for word in ["why", "then", "camera", "secret", "mystery", "story"]) else 8
    low_competition = (100 - _competition_score(trend)) * 0.24
    return _clamp(45 + mystery + low_competition, 0, 100)


def _payoff_score(trend: dict) -> float:
    category = trend.get("category", "")
    payoff_categories = {"Funny Animals", "Funny Fails", "Horror Stories", "Sports Drama", "Survival Stories", "Crazy Facts"}
    base = 78 if category in payoff_categories else 70
    return _clamp(base + min(len(trend.get("evidence", [])) * 4, 10), 0, 100)


def _shareability_score(trend: dict, emotional_score: float) -> float:
    comments = min(trend.get("reddit_ups", 0) / 1000, 28)
    likes = min(trend.get("youtube_likes", 0) / 5000, 24)
    return _clamp(35 + (emotional_score * 0.28) + comments + likes, 0, 100)


def _age_hours(value: str) -> float:
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 48
    return max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 1)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
