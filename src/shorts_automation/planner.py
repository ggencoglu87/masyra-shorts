from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .scoring import score_trend


def build_daily_network_plan(trends: list[dict], channel_name: str, top_n: int = 10) -> dict:
    scored = []
    for trend in trends:
        scores = score_trend(trend)
        scored.append({**trend, **scores})

    ranked = sorted(scored, key=lambda item: item["viral_potential_score"], reverse=True)[:top_n]
    items = [make_content_item(trend, rank=index + 1, channel_name=channel_name) for index, trend in enumerate(ranked)]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel_name": channel_name,
        "network_strategy": "trend-following Shorts network",
        "selection_rule": f"Top {top_n} by viral_potential_score",
        "items": items,
    }


def make_content_item(trend: dict, rank: int, channel_name: str) -> dict:
    topic = normalize_topic(trend["title"])
    title = make_title(topic, trend["category"])
    script = make_script(topic, trend["category"], channel_name)
    narration = make_narration(topic, trend["category"], channel_name)
    hashtags = build_hashtags(topic, trend["category"])

    return {
        "rank": rank,
        "trend": {
            "title": trend["title"],
            "category": trend["category"],
            "sources": trend.get("sources", []),
            "evidence": trend.get("evidence", []),
            "urls": trend.get("urls", []),
        },
        "scores": {
            "trend_score": trend["trend_score"],
            "growth_score": trend["growth_score"],
            "competition_score": trend["competition_score"],
            "viral_potential_score": trend["viral_potential_score"],
        },
        "creative_rules": [
            "Do not copy trend videos.",
            "Do not use copyrighted footage.",
            "Use only the theme, public facts, and original commentary.",
        ],
        "title": title,
        "description": f"{channel_name} original short inspired by the trend theme: {topic}.",
        "script": script,
        "narration": narration,
        "hashtags": hashtags,
        "production": {
            "format": "vertical 9:16",
            "duration_target_seconds": 42,
            "visual_style": visual_style_for_category(trend["category"]),
            "asset_policy": "Use generated visuals, licensed stock, public-domain material, or original screen graphics only.",
        },
    }


def write_video_packages(plan: dict, output_root: Path) -> list[Path]:
    written: list[Path] = []
    videos_dir = output_root / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    for item in plan["items"]:
        slug = f"{item['rank']:02d}-{slugify(item['title'])}"
        video_dir = videos_dir / slug
        video_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "script.txt": item["script"],
            "voiceover.txt": item["narration"],
            "subtitles.srt": make_subtitles(item["narration"]),
            "asset-prompts.json": json.dumps(make_asset_prompts(item), ensure_ascii=False, indent=2),
            "copyright-checklist.json": json.dumps(make_copyright_checklist(item), ensure_ascii=False, indent=2),
            "upload-metadata.json": json.dumps(
                {
                    "title": item["title"],
                    "description": item["description"],
                    "hashtags": item["hashtags"],
                    "status": "ready_for_upload_after_render",
                },
                ensure_ascii=False,
                indent=2,
            ),
            "video-plan.json": json.dumps(item, ensure_ascii=False, indent=2),
            "render-brief.txt": make_render_brief(item),
        }

        for filename, content in files.items():
            path = video_dir / filename
            path.write_text(content, encoding="utf-8")
            written.append(path)

    return written


def make_asset_prompts(item: dict) -> dict:
    category = item["trend"]["category"]
    topic = item["trend"]["title"]
    style = item["production"]["visual_style"]
    return {
        "policy": "Generate or source original/licensed assets only. Do not recreate source video frames or copyrighted clips.",
        "scenes": [
            {
                "scene": 1,
                "time": "0-3s",
                "type": "image_or_motion_background",
                "prompt": f"Vertical 9:16 hook visual for {category}: abstract viral trend energy, bold empty space for captions, {style}. No logos, no celebrities, no copyrighted footage.",
            },
            {
                "scene": 2,
                "time": "3-12s",
                "type": "explainer_visual",
                "prompt": f"Original explainer graphic about the theme '{topic}', simple shapes, clean information design, vertical composition, no copied source imagery.",
            },
            {
                "scene": 3,
                "time": "12-25s",
                "type": "supporting_visual",
                "prompt": f"Original visual metaphor showing why a {category} trend spreads quickly, kinetic text-friendly layout, licensed or generated look.",
            },
            {
                "scene": 4,
                "time": "25-38s",
                "type": "brand_take_visual",
                "prompt": "Masyra Labs analysis moment, sleek vertical dashboard style, trend score cards, subtle motion graphics, no third-party marks.",
            },
            {
                "scene": 5,
                "time": "38-45s",
                "type": "cta_visual",
                "prompt": "Clean vertical end card with room for a short question, Masyra Labs brand text, high contrast, no copyrighted media.",
            },
        ],
    }


def make_copyright_checklist(item: dict) -> dict:
    return {
        "status": "pending_review",
        "required_before_approval": [
            "No copied source trend footage.",
            "No copyrighted movie, TV, sports broadcast, music video, or gameplay clips unless explicitly licensed.",
            "No celebrity likeness asset unless it is licensed, public-domain, or used as lawful editorial commentary with proper context.",
            "All stock footage/images have a license recorded outside the package.",
            "Generated assets do not imitate a living artist, brand logo, or protected character.",
            "Voiceover is original and does not clone a real person's voice without permission.",
            "Music/sound effects, if added later, are licensed or generated with commercial rights.",
            "Upload metadata does not claim ownership of source videos or imply affiliation with third parties.",
        ],
        "creative_basis": item["creative_rules"],
        "asset_policy": item["production"]["asset_policy"],
    }


def make_script(topic: str, category: str, channel_name: str) -> str:
    return "\n".join(
        [
            f"0-3s HOOK: Everyone is talking about this {category.lower()} trend, but the real question is why it spread so fast.",
            f"3-12s CONTEXT: The theme is {topic}. Keep the visuals original and explain the idea without copying any source video.",
            "12-25s TURN: Point out the surprising detail, the emotional trigger, or the simple reason people keep sharing it.",
            f"25-38s PAYOFF: Give the {channel_name} take in one clear sentence that feels useful, funny, or unexpected.",
            "38-45s CTA: Ask a short question that invites comments without begging for engagement.",
        ]
    )


def make_narration(topic: str, category: str, channel_name: str) -> str:
    return (
        f"This {category.lower()} trend is moving fast: {topic}. "
        "Instead of copying the viral clip, look at the pattern behind it. "
        "People share it because it is easy to understand in one second, but it still leaves a question open. "
        f"The {channel_name} angle is simple: turn the trend into a clean, original explanation with a stronger ending. "
        "What part of this trend do you think made it blow up?"
    )


def make_subtitles(narration: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", narration) if sentence.strip()]
    blocks = []
    start = 0
    for index, sentence in enumerate(sentences, start=1):
        end = start + max(3, min(7, len(sentence.split()) // 2))
        blocks.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{sentence}\n")
        start = end
    return "\n".join(blocks)


def make_render_brief(item: dict) -> str:
    return "\n".join(
        [
            "Render target: 1080x1920, 30fps, 35-45 seconds.",
            f"Category: {item['trend']['category']}",
            f"Visual style: {item['production']['visual_style']}",
            "Footage rule: no copied trend footage and no copyrighted clips.",
            "Use generated backgrounds, kinetic text, charts, icons, simple reenactments, or licensed media.",
        ]
    )


def make_title(topic: str, category: str) -> str:
    base = topic if len(topic) <= 52 else f"{topic[:49].rstrip()}..."
    prefixes = {
        "AI": "This AI Trend Is Moving Fast",
        "Gaming": "Gamers Are Sharing This",
        "Horror Stories": "This Creepy Trend Has a Twist",
        "Funny Kids": "This Funny Kid Moment Exploded",
        "Animals": "This Animal Trend Is Everywhere",
        "Sports": "Sports Fans Are Talking About This",
        "Celebrity": "This Celebrity Trend Is Blowing Up",
        "Movies & TV": "This Movie & TV Trend Is Spreading",
        "Viral News": "This Viral News Trend Is Everywhere",
        "Misc Viral": "This Trend Is Suddenly Everywhere",
    }
    return f"{prefixes.get(category, 'This Trend Is Suddenly Everywhere')}: {base} #shorts"


def build_hashtags(topic: str, category: str) -> list[str]:
    category_tags = {
        "Sports": "sports",
        "Horror Stories": "horror",
        "Funny Kids": "funnykids",
        "Viral News": "viralnews",
        "Gaming": "gaming",
        "AI": "ai",
        "Celebrity": "celebrity",
        "Animals": "animals",
        "Movies & TV": "moviestv",
        "Misc Viral": "viral",
    }
    seed = ["shorts", "masyralabs", "trend", category_tags.get(category, "viral")]
    seed.extend(re.findall(r"[A-Za-z0-9]{4,}", topic.lower())[:4])
    unique = []
    for tag in seed:
        tag = re.sub(r"[^A-Za-z0-9]", "", tag)
        if tag and tag not in unique:
            unique.append(tag)
    return [f"#{tag}" for tag in unique[:8]]


def visual_style_for_category(category: str) -> str:
    styles = {
        "Sports": "fast kinetic stats, scoreboard overlays, original motion graphics",
        "Horror Stories": "dark original illustrations, suspense captions, no copied footage",
        "Funny Kids": "bright kinetic text, playful icons, original reenactment graphics",
        "Viral News": "clean news desk graphics, maps, timelines, bold captions",
        "Gaming": "original UI-style graphics, controller shots, generated gameplay-like backgrounds",
        "AI": "screen graphics, abstract model diagrams, futuristic generated visuals",
        "Celebrity": "timeline cards, silhouette graphics, public-domain or licensed images only",
        "Animals": "licensed stock or generated animal scenes, warm captions",
        "Movies & TV": "original review graphics, no copyrighted clips",
        "Misc Viral": "high-contrast kinetic typography and original explainer visuals",
    }
    return styles.get(category, styles["Misc Viral"])


def normalize_topic(title: str) -> str:
    cleaned = re.sub(r"[|#@]+", " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100].rstrip(" -:")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return slug.strip("-")[:70] or "trend"


def _srt_time(seconds: int) -> str:
    return f"00:00:{seconds:02d},000"
