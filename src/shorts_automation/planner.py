from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .character_bible import build_character_bible, character_prompt_text
from .scoring import score_trend
from .studio_memory import update_studio_memory


VIRAL_CATEGORIES = [
    "Funny Animals",
    "Funny Kids",
    "Funny Fails",
    "Horror Stories",
    "Reddit Stories",
    "Sports Drama",
    "Relationship Stories",
    "Minecraft Stories",
    "Motivational Stories",
    "Celebrity Drama",
    "Survival Stories",
    "Crazy Facts",
]

CHANNEL_BY_CATEGORY = {
    "Funny Animals": "animals",
    "Funny Kids": "kids",
    "Funny Fails": "kids",
    "Horror Stories": "horror",
    "Reddit Stories": "reddit",
    "Sports Drama": "sports",
    "Relationship Stories": "reddit",
    "Minecraft Stories": "minecraft",
    "Motivational Stories": "reddit",
    "Celebrity Drama": "reddit",
    "Survival Stories": "reddit",
    "Crazy Facts": "reddit",
}

VOICE_PROFILES = {
    "Funny Animals": {"style": "energetic", "pace": "quick", "emotion": "playful surprise"},
    "Funny Kids": {"style": "energetic", "pace": "quick", "emotion": "warm comedy"},
    "Funny Fails": {"style": "energetic", "pace": "quick", "emotion": "chaotic comedy"},
    "Horror Stories": {"style": "slow and suspenseful", "pace": "slow", "emotion": "dread"},
    "Reddit Stories": {"style": "confessional storyteller", "pace": "medium", "emotion": "curious tension"},
    "Sports Drama": {"style": "excited commentator", "pace": "fast", "emotion": "high stakes"},
    "Relationship Stories": {"style": "dramatic storyteller", "pace": "medium", "emotion": "betrayal and reveal"},
    "Minecraft Stories": {"style": "fast gamer narration", "pace": "fast", "emotion": "adventure"},
    "Motivational Stories": {"style": "inspiring", "pace": "medium", "emotion": "hopeful intensity"},
    "Celebrity Drama": {"style": "dramatic entertainment host", "pace": "fast", "emotion": "tea and suspense"},
    "Survival Stories": {"style": "urgent documentary narrator", "pace": "medium", "emotion": "danger"},
    "Crazy Facts": {"style": "excited fact narrator", "pace": "fast", "emotion": "shock"},
}


def build_daily_network_plan(trends: list[dict], channel_name: str, top_n: int = 10) -> dict:
    scored = []
    for trend in trends:
        entertainment_trend = {**trend, "category": normalize_viral_category(trend.get("category", ""), trend.get("title", ""))}
        scores = score_trend(entertainment_trend)
        scored.append({**entertainment_trend, **scores})

    ranked = sorted(scored, key=lambda item: item["viral_score"], reverse=True)[:top_n]
    items = [make_content_item(trend, rank=index + 1, channel_name=channel_name) for index, trend in enumerate(ranked)]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel_name": channel_name,
        "network_strategy": "autonomous viral entertainment Shorts studio",
        "selection_rule": f"Top {top_n} by viral_score and completion probability",
        "success_metric": "Would someone stop scrolling and watch this?",
        "items": items,
    }


def make_content_item(trend: dict, rank: int, channel_name: str) -> dict:
    topic = normalize_topic(trend["title"])
    category = normalize_viral_category(trend["category"], topic)
    story = build_story(topic, category)
    character_bible = build_character_bible(category)
    title = make_title(story["hook"], category)
    script = make_script(story, category)
    narration = make_narration(story, category)
    storyboard = make_storyboard(story, category, character_bible)
    hashtags = build_hashtags(topic, category)

    return {
        "rank": rank,
        "trend": {
            "title": trend["title"],
            "category": category,
            "sources": trend.get("sources", []),
            "evidence": trend.get("evidence", []),
            "urls": trend.get("urls", []),
        },
        "universe": character_bible.get("universe", {}),
        "scores": {
            "trend_score": trend["trend_score"],
            "growth_score": trend["growth_score"],
            "competition_score": trend["competition_score"],
            "momentum_score": trend["momentum_score"],
            "viral_potential_score": trend["viral_potential_score"],
            "hook_score": trend["hook_score"],
            "curiosity_score": trend["curiosity_score"],
            "payoff_score": trend["payoff_score"],
            "shareability_score": trend["shareability_score"],
            "completion_probability": trend["completion_probability"],
            "rewatch_probability": trend["rewatch_probability"],
            "viral_score": trend["viral_score"],
            "publish_ready": trend["publish_ready"],
        },
        "trend_intelligence": explain_trend({**trend, "category": category}),
        "content_strategy": {
            "hook": story["hook"],
            "story_structure": "hook -> curiosity -> escalation -> twist -> payoff",
            "retention_plan": [
                "Open with a curiosity trigger in the first 3 seconds.",
                "Introduce conflict before second 10.",
                "Escalate with a new problem before second 20.",
                "Pay off with a twist or emotional release before second 30.",
            ],
            "cta": story["cta"],
        },
        "creative_rules": [
            "Do not copy trend videos.",
            "Do not use copyrighted footage.",
            "Use only the theme, public facts, and original commentary.",
        ],
        "title": title,
        "description": f"Original YouTube Short inspired by the trending theme: {topic}.",
        "script": script,
        "narration": narration,
        "storyboard": storyboard,
        "character_bible": character_bible,
        "voice_profile": VOICE_PROFILES[category],
        "channel_target": CHANNEL_BY_CATEGORY[category],
        "hashtags": hashtags,
        "production": {
            "format": "vertical 9:16",
            "duration_target_seconds": 26,
            "caption_style": "TikTok word-by-word large burned captions",
            "visual_style": visual_style_for_category(category),
            "asset_policy": "Use AI-generated character images and AI scene videos first. Stock footage is fallback only.",
            "publish_gate": "Publish-ready requires real AI generated scene videos. Image-only, image-motion, FFmpeg motion, and stock fallback are not publish-ready.",
        },
        "copyright_safe": True,
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
            "captions.json": json.dumps(make_word_captions(item["narration"]), ensure_ascii=False, indent=2),
            "storyboard.json": json.dumps(item["storyboard"], ensure_ascii=False, indent=2),
            "character_bible.json": json.dumps(item["character_bible"], ensure_ascii=False, indent=2),
            "voice_profile.json": json.dumps(item["voice_profile"], ensure_ascii=False, indent=2),
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
        update_studio_memory(output_root, video_dir, item)

    return written


def make_asset_prompts(item: dict) -> dict:
    category = item["trend"]["category"]
    style = item["production"]["visual_style"]
    storyboard = item.get("storyboard", [])
    character_bible = item.get("character_bible", {})
    return {
        "policy": "Primary visual path is true AI-generated cinematic character video scenes. Image-only and image-motion are preview fallbacks only.",
        "style": character_bible.get("style", ""),
        "characters": character_bible.get("characters", []),
        "scenes": [
            {
                "scene": scene["scene"],
                "time": scene["time"],
                "type": "ai_character_scene_image",
                "prompt": scene["image_prompt"],
                "negative_prompt": scene["negative_prompt"],
                "search_queries": scene["search_queries"],
            }
            for scene in storyboard
        ],
    }


def make_copyright_checklist(item: dict) -> dict:
    return {
        "status": "pending_review",
        "required_before_approval": [
            "No copied source trend footage.",
            "No copyrighted movie, TV, sports broadcast, music video, or gameplay clips unless explicitly licensed.",
            "No celebrity likeness asset unless it is licensed, public-domain, or used as lawful editorial commentary with proper context.",
            "AI character images and videos are original generations.",
            "Any stock footage/images used as fallback have a license recorded outside the package.",
            "Generated assets do not imitate a living artist, brand logo, or protected character.",
            "Voiceover is original and does not clone a real person's voice without permission.",
            "Music/sound effects, if added later, are licensed or generated with commercial rights.",
            "Upload metadata does not claim ownership of source videos or imply affiliation with third parties.",
        ],
        "creative_basis": item["creative_rules"],
        "asset_policy": item["production"]["asset_policy"],
        "copyright_safe": item.get("copyright_safe", False),
        "source_metadata": item["trend"].get("sources", []),
    }


def explain_trend(trend: dict) -> dict:
    category = trend.get("category", "viral")
    sources = ", ".join(trend.get("sources", [])) or "trend signals"
    return {
        "why_trending": f"It is gaining attention across {sources}, with enough velocity to stand out in {category}.",
        "why_viewers_watch": "The idea is simple to understand quickly, but leaves a curiosity gap that keeps viewers waiting.",
        "why_it_might_go_viral": "It has a clear emotional trigger, easy remix potential, and a comment-friendly ending.",
    }


def make_script(story: dict, category: str) -> str:
    return "\n".join(
        [
            f"0-3s HOOK: {story['hook']}",
            f"3-10s CURIOSITY: {story['curiosity']}",
            f"10-20s ESCALATION: {story['escalation']}",
            f"20-26s TWIST: {story['twist']}",
            f"26-30s PAYOFF: {story['payoff']}",
        ]
    )


def make_narration(story: dict, category: str) -> str:
    return " ".join([story["hook"], story["curiosity"], story["escalation"], story["twist"], story["payoff"], story["cta"]])


def make_subtitles(narration: str) -> str:
    words = [word.strip() for word in narration.split() if word.strip()]
    blocks = []
    for index, word in enumerate(words[:72], start=1):
        start = (index - 1) * 0.35
        end = start + 0.34
        blocks.append(f"{index}\n{_srt_time_float(start)} --> {_srt_time_float(end)}\n{word.upper()}\n")
    return "\n".join(blocks)


def make_word_captions(narration: str) -> list[dict]:
    return [
        {"word": word.strip(".,!?;:").upper(), "start": round(index * 0.35, 2), "end": round((index * 0.35) + 0.34, 2)}
        for index, word in enumerate(narration.split()[:72])
        if word.strip()
    ]


def make_render_brief(item: dict) -> str:
    return "\n".join(
        [
            "Render target: 1080x1920, 30fps, 20-45 seconds.",
            f"Category: {item['trend']['category']}",
            f"Channel target: {item['channel_target']}",
            f"Voice style: {item['voice_profile']['style']}",
            f"Visual style: {item['production']['visual_style']}",
            "Footage rule: no copied trend footage and no copyrighted clips.",
            "Renderer production priority: real AI scene videos only. Image motion and still images are preview fallbacks and are not publish-ready.",
        ]
    )


def make_title(topic: str, category: str) -> str:
    base = topic.replace("...", "").strip()
    return f"{base[:58].rstrip()} #shorts"


def build_hashtags(topic: str, category: str) -> list[str]:
    category_tags = {
        "Sports Drama": "sports",
        "Horror Stories": "horror",
        "Funny Kids": "funnykids",
        "Funny Animals": "funnyanimals",
        "Funny Fails": "fails",
        "Reddit Stories": "redditstories",
        "Relationship Stories": "relationship",
        "Minecraft Stories": "minecraft",
        "Motivational Stories": "motivation",
        "Celebrity Drama": "celebritydrama",
        "Survival Stories": "survival",
        "Crazy Facts": "crazyfacts",
    }
    seed = ["shorts", "fyp", "viral", category_tags.get(category, "story")]
    seed.extend(re.findall(r"[A-Za-z0-9]{4,}", topic.lower())[:4])
    unique = []
    for tag in seed:
        tag = re.sub(r"[^A-Za-z0-9]", "", tag)
        if tag and tag not in unique:
            unique.append(tag)
    return [f"#{tag}" for tag in unique[:8]]


def visual_style_for_category(category: str) -> str:
    styles = {
        "Funny Animals": "real pets, funny reactions, quick cuts",
        "Funny Kids": "playful home-video energy, bright reactions",
        "Funny Fails": "fast action, near-miss comedy, reaction shots",
        "Horror Stories": "dark hallway, shadows, suspenseful close-ups",
        "Reddit Stories": "POV reenactment, phone text, expressive faces",
        "Sports Drama": "crowd tension, scoreboard pressure, celebration",
        "Relationship Stories": "dramatic texting, emotional close-ups",
        "Minecraft Stories": "blocky survival world, cave suspense, gaming motion",
        "Motivational Stories": "cinematic struggle, sunrise payoff, human grit",
        "Celebrity Drama": "red carpet silhouettes, paparazzi-style flashes, no likeness copying",
        "Survival Stories": "wilderness danger, urgent movement, rescue tension",
        "Crazy Facts": "surprising real-world objects, bold reaction visuals",
    }
    return styles.get(category, styles["Reddit Stories"])


def build_story(topic: str, category: str) -> dict:
    templates = {
        "Funny Animals": ("Nobody expected this animal to fight back.", "A tiny pet got blamed for the mess.", "Then the camera caught the real troublemaker.", "The guilty one tried to act normal.", "But the evidence was literally stuck to its face.", "Would your pet get away with this?"),
        "Funny Kids": ("This kid had one job.", "Everyone thought the answer would be simple.", "Then the explanation got way too confident.", "The room went silent for one second.", "And somehow the kid was technically right.", "Would you have laughed or given full credit?"),
        "Funny Fails": ("Watch what happens next.", "The plan looked perfect for about two seconds.", "Then one tiny mistake changed everything.", "Everybody froze before the crash.", "The recovery was funnier than the fail.", "Would you try this again?"),
        "Horror Stories": ("Nobody believed the knocking was real.", "A boy heard it every night at 3 AM.", "Then he finally checked the camera.", "The hallway was empty, but the door moved.", "The knock came from inside the room.", "Would you watch the rest of the footage?"),
        "Reddit Stories": ("I thought my roommate was harmless.", "Then food started disappearing every night.", "I set up one small trap.", "The next morning, the note on the fridge was gone.", "But my camera caught who wrote it.", "What would you do next?"),
        "Sports Drama": ("The game looked completely over.", "They were down by 30 and the crowd was leaving.", "Then the bench player asked for one chance.", "The first shot went in, then the second.", "By the final buzzer, nobody was sitting down.", "Best comeback or pure luck?"),
        "Relationship Stories": ("She found one text that changed everything.", "At first it looked like a normal reminder.", "Then she noticed the contact name was fake.", "He said it was a joke, but the timing made no sense.", "So she replied from his phone.", "Would you forgive this?"),
        "Minecraft Stories": ("My friend told me not to dig down.", "I did it anyway because the cave sounded empty.", "Then my torch went out.", "Something moved behind the diamonds.", "The base was never ours.", "Would you log out or keep mining?"),
        "Motivational Stories": ("Everyone counted him out.", "He failed the same test three times.", "On the fourth try, he stopped trying to look talented.", "He practiced the boring part every single day.", "Six months later, they asked how he got lucky.", "What would you start today?"),
        "Celebrity Drama": ("One red carpet reaction said everything.", "The smile lasted half a second too long.", "Then another celebrity looked away.", "Fans replayed the clip until they found the moment.", "The real drama was not what anyone expected.", "Did you catch it the first time?"),
        "Survival Stories": ("He had ten seconds to choose.", "The trail disappeared under fresh snow.", "His phone had one percent battery.", "Then he saw footprints going the wrong direction.", "Following them saved his life.", "Would you have followed them?"),
        "Crazy Facts": ("This sounds fake, but it is real.", "There is an animal that can survive something impossible.", "Scientists tested it again and again.", "The weirdest part is what wakes it back up.", "It basically hits pause on life.", "What fact should we do next?"),
    }
    hook, curiosity, escalation, twist, payoff, cta = templates[category]
    return {
        "topic_seed": topic,
        "hook": hook,
        "curiosity": curiosity,
        "escalation": escalation,
        "twist": twist,
        "payoff": payoff,
        "cta": cta,
    }


def make_storyboard(story: dict, category: str, character_bible: dict) -> list[dict]:
    labels = [
        ("Hook", "0-3s", 3, story["hook"], "slow push-in, cinematic close-up", "shock and curiosity"),
        ("Conflict", "3-8s", 5, story["curiosity"], "side tracking shot, expressive reaction", "accusation and tension"),
        ("Escalation", "8-16s", 8, story["escalation"], "handheld animated camera, quick reveal", "panic and surprise"),
        ("Twist", "16-24s", 8, story["twist"], "dramatic low angle, fast character motion", "comic reversal"),
        ("Payoff", "24-30s", 6, story["payoff"], "wide shot into punchline close-up", "funny payoff"),
    ]
    character_ids = [character["id"] for character in character_bible.get("characters", [])]
    character_text = character_prompt_text(character_bible)
    scenes = []
    for index, (beat, time_range, duration, text, camera, emotion) in enumerate(labels, start=1):
        visual_action = visual_prompt_for_scene(category, text)
        prompt_base = (
            f"{visual_action}. Characters: {character_text}. "
            f"Style: {character_bible.get('style', '')}. Same character design, same clothing, same proportions, cinematic 9:16."
        )
        scenes.append(
            {
                "scene": index,
                "beat": beat,
                "time": time_range,
                "duration": duration,
                "narration": text,
                "caption": text,
                "visual_action": visual_action,
                "camera": camera,
                "emotion": emotion,
                "characters": character_ids,
                "visual_prompt": visual_action,
                "image_prompt": prompt_base,
                "video_prompt": f"{prompt_base} Smooth animated motion, expressive faces, cinematic lighting, no text.",
                "negative_prompt": "low quality, blurry, inconsistent character, extra limbs, deformed face, text, watermark, logo, different outfit, different species",
                "search_queries": scene_search_queries(category, text),
            }
        )
    return scenes


def visual_prompt_for_scene(category: str, text: str) -> str:
    return f"Story moment: {text}"


def scene_search_queries(category: str, text: str) -> list[str]:
    lower = text.lower()
    seeds = {
        "Funny Animals": ["cat reaction", "pet surprise", "animal funny"],
        "Funny Kids": ["kid funny reaction", "child surprised", "family laughing"],
        "Funny Fails": ["funny fail", "people surprised", "near miss"],
        "Horror Stories": ["scary dark hallway", "door knocking", "security camera night"],
        "Reddit Stories": ["roommate argument", "phone text drama", "apartment kitchen"],
        "Sports Drama": ["sports celebration", "basketball comeback", "crowd cheering"],
        "Relationship Stories": ["couple argument", "text message reaction", "woman shocked phone"],
        "Minecraft Stories": ["minecraft cave", "gaming setup", "block world"],
        "Motivational Stories": ["person training", "runner sunrise", "emotional success"],
        "Celebrity Drama": ["red carpet cameras", "paparazzi flash", "celebrity event"],
        "Survival Stories": ["snow trail", "wilderness survival", "rescue helicopter"],
        "Crazy Facts": ["amazing animal", "science experiment", "surprised reaction"],
    }
    words = [word for word in re.findall(r"[a-z]{4,}", lower) if word not in {"this", "that", "then", "with", "from", "they", "were"}]
    phrase = " ".join(words[:2])
    queries = list(seeds[category])
    if phrase:
        queries.insert(0, phrase)
    return queries[:4]


def normalize_viral_category(category: str, title: str = "") -> str:
    value = f"{category} {title}".lower()
    tokens = set(re.findall(r"[a-z]+", value))
    if "animal" in tokens or "animals" in tokens or "dog" in tokens or "dogs" in tokens or "cat" in tokens or "cats" in tokens:
        return "Funny Animals"
    if "kid" in value or "child" in value:
        return "Funny Kids"
    if "horror" in value or "scary" in value or "doorbell" in value:
        return "Horror Stories"
    if "sport" in value or "basketball" in value or "game" in value and "minecraft" not in value:
        return "Sports Drama"
    if "minecraft" in value:
        return "Minecraft Stories"
    if "celebrity" in value or "red carpet" in value:
        return "Celebrity Drama"
    if "fact" in value or "science" in value:
        return "Crazy Facts"
    if "fail" in value:
        return "Funny Fails"
    if "survival" in value or "rescue" in value:
        return "Survival Stories"
    if "relationship" in value or "girlfriend" in value or "boyfriend" in value:
        return "Relationship Stories"
    if "motiv" in value:
        return "Motivational Stories"
    return "Reddit Stories"


def normalize_topic(title: str) -> str:
    cleaned = re.sub(r"[|#@]+", " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100].rstrip(" -:")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return slug.strip("-")[:70] or "trend"


def _srt_time(seconds: int) -> str:
    return f"00:00:{seconds:02d},000"


def _srt_time_float(seconds: float) -> str:
    whole = int(seconds)
    millis = int((seconds - whole) * 1000)
    return f"00:00:{whole:02d},{millis:03d}"
