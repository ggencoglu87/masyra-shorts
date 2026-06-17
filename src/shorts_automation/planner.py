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
    character_bible = build_character_bible(category)
    story = build_story(topic, category, character_bible)
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
            "story_structure": "hook -> conflict -> escalation -> payoff",
            "episode_premise": story["episode_premise"],
            "series_goal": "episodic AI animated short with recurring characters and universe memory",
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
            "duration_target_seconds": 30,
            "duration_range_seconds": [25, 35],
            "minimum_dialogue_lines": 20,
            "minimum_character_dialogue_percentage": 30,
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
            "voiceover.txt": make_dialogue_script(item["storyboard"]),
            "subtitles.srt": make_dialogue_subtitles(item["storyboard"]),
            "captions.json": json.dumps(make_dialogue_captions(item["storyboard"]), ensure_ascii=False, indent=2),
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
            f"3-10s CONFLICT: {story['conflict']}",
            f"10-18s ESCALATION: {story['escalation']}",
            f"18-25s TWIST: {story['twist']}",
            f"25-30s PAYOFF: {story['payoff']}",
        ]
    )


def make_narration(story: dict, category: str) -> str:
    return " ".join([story["hook"], story["conflict"], story["escalation"], story["twist"], story["payoff"], story["cta"]])


def make_dialogue_script(storyboard: list[dict]) -> str:
    lines = []
    for dialogue in _dialogue_lines(storyboard):
        lines.append(f"{dialogue['speaker_id'].upper()}: {dialogue['line']}")
    return "\n".join(lines)


def make_dialogue_subtitles(storyboard: list[dict]) -> str:
    blocks = []
    for index, dialogue in enumerate(_dialogue_lines(storyboard), start=1):
        label = _speaker_caption(dialogue["speaker_id"])
        text = f"{label}: {dialogue['line'].upper()}"
        blocks.append(f"{index}\n{_srt_time_float(float(dialogue['start']))} --> {_srt_time_float(float(dialogue['end']))}\n{text}\n")
    return "\n".join(blocks)


def make_dialogue_captions(storyboard: list[dict]) -> list[dict]:
    captions = []
    for dialogue in _dialogue_lines(storyboard):
        words = [word.strip(".,!?;:") for word in dialogue["line"].split() if word.strip(".,!?;:")]
        if not words:
            continue
        start = float(dialogue["start"])
        end = float(dialogue["end"])
        step = max(0.18, (end - start) / max(len(words), 1))
        speaker = _speaker_caption(dialogue["speaker_id"])
        for index, word in enumerate(words):
            captions.append(
                {
                    "speaker_id": dialogue["speaker_id"],
                    "speaker": speaker,
                    "word": word.upper(),
                    "start": round(start + (index * step), 2),
                    "end": round(min(end, start + ((index + 1) * step)), 2),
                }
            )
    return captions


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


def _dialogue_lines(storyboard: list[dict]) -> list[dict]:
    lines = []
    for scene in storyboard:
        for dialogue in scene.get("dialogue", []):
            if dialogue.get("line"):
                lines.append(dialogue)
    return lines


def _speaker_caption(speaker_id: str) -> str:
    if speaker_id == "narrator":
        return "NARRATOR"
    parts = speaker_id.split("_")
    return (parts[0] if parts else speaker_id).upper()


def make_render_brief(item: dict) -> str:
    return "\n".join(
        [
            "Render target: 1080x1920, 30fps, 20-45 seconds.",
            f"Category: {item['trend']['category']}",
            f"Universe: {item['universe'].get('name', '')}",
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


def build_story(topic: str, category: str, character_bible: dict | None = None) -> dict:
    universe = (character_bible or build_character_bible(category)).get("universe", {})
    universe_id = universe.get("id", "")
    templates = {
        "farm_chaos": (
            "Bob promised he was done causing trouble.",
            "Then Carl found muddy paw prints leading straight to the prize pie.",
            "Bob tried to hide the evidence, but every farm animal started following the smell.",
            "Carl revealed a second trail of crumbs going under Bob's hat.",
            "The pie was safe the whole time, because Carl had hidden it from Bob first.",
            "Would Carl survive one day without making Bob look guilty?",
        ),
        "forest_legends": (
            "Willow heard the forest whisper her name.",
            "Bramble begged her not to follow the glowing footprints past the old stone gate.",
            "The footprints split into two trails, and one trail copied Willow's voice perfectly.",
            "The fake voice started answering questions only Bramble should know.",
            "The voice was a scared baby moon-moth trying to find its way home.",
            "Would you follow the voice or run back?",
        ),
        "space_academy": (
            "Nova had thirty seconds before the simulator exploded.",
            "Zip said the rules were clear: never touch the red gravity switch.",
            "Nova touched it anyway, and the whole academy cafeteria floated into orbit.",
            "The simulator announced the explosion was actually a surprise exam.",
            "The switch saved everyone, but Zip had already filed a panic report.",
            "Would Nova get detention or a medal?",
        ),
        "funny_pets": (
            "Pixel swore he did not eat the missing sandwich.",
            "Miso noticed one tiny crumb stuck to Pixel's green bow tie.",
            "Pixel staged a fake investigation, but every clue pointed back to his nap bed.",
            "The final clue was a perfect paw print on Miso's own plate.",
            "Miso had eaten the sandwich too, and only framed Pixel to make him confess first.",
            "Which pet would you trust?",
        ),
        "monster_school": (
            "Milo heard knocking from the locker nobody opens.",
            "Nora dared him to answer before the bell rang.",
            "The locker whispered Milo's homework answers in his own voice.",
            "Then the locker begged them not to tell the teacher.",
            "Inside was a tiny scared echo monster asking to join class.",
            "Would you open the locker?",
        ),
    }
    hook, conflict, escalation, twist, payoff, cta = templates.get(universe_id, templates["space_academy"])
    return {
        "topic_seed": topic,
        "universe": universe,
        "episode_premise": f"{universe.get('name', 'Animated Universe')} episode inspired by: {topic}",
        "hook": hook,
        "conflict": conflict,
        "curiosity": conflict,
        "escalation": escalation,
        "twist": twist,
        "payoff": payoff,
        "cta": cta,
    }


def make_storyboard(story: dict, category: str, character_bible: dict) -> list[dict]:
    labels = [
        ("Hook", "0-3s", 3, story["hook"], "slow push-in, cinematic close-up", "shock and curiosity"),
        ("Conflict", "3-10s", 7, story["conflict"], "side tracking shot, expressive reaction", "accusation and tension"),
        ("Escalation", "10-18s", 8, story["escalation"], "dynamic handheld animated camera, quick reveal, foreground character reaction", "panic and surprise"),
        ("Twist", "18-25s", 7, story["twist"], "dramatic low angle, fast character motion, reaction insert", "shocked reversal"),
        ("Payoff", "25-30s", 5, story["payoff"], "wide shot into punchline close-up, clean final pose", "comic reversal and emotional payoff"),
    ]
    character_ids = [character["id"] for character in character_bible.get("characters", [])]
    character_text = character_prompt_text(character_bible)
    universe = character_bible.get("universe", {})
    environment = universe.get("environment", "stylized cinematic animated set")
    primary = character_ids[0] if character_ids else "narrator"
    secondary = character_ids[1] if len(character_ids) > 1 else primary
    scenes = []
    for index, (beat, time_range, duration, text, camera, emotion) in enumerate(labels, start=1):
        scene_start = _time_range_start(time_range)
        dialogue = _scene_dialogue(index, beat, text, primary, secondary, scene_start, duration, emotion)
        visual_action = visual_prompt_for_scene(category, text)
        prompt_base = _minimax_scene_prompt(
            visual_action=visual_action,
            character_text=character_text,
            environment=environment,
            camera=camera,
            emotion=emotion,
            style=character_bible.get("style", ""),
        )
        scenes.append(
            {
                "scene": index,
                "beat": beat,
                "time": time_range,
                "duration": duration,
                "narration": text,
                "caption": text,
                "dialogue": dialogue,
                "visual_action": visual_action,
                "camera": camera,
                "emotion": emotion,
                "emotional_state": emotion,
                "environment": environment,
                "characters": character_ids,
                "visual_prompt": visual_action,
                "image_prompt": prompt_base,
                "video_prompt": f"{prompt_base} Minimax video: smooth character animation, clear body motion, expressive faces, stable identity, cinematic lighting, no text.",
                "negative_prompt": "low quality, blurry, inconsistent character, extra limbs, deformed face, text, watermark, logo, different outfit, different species",
                "search_queries": scene_search_queries(category, text),
            }
        )
    return _ensure_story_minimums(scenes, primary, secondary)


def _scene_dialogue(scene_index: int, beat: str, narration: str, primary: str, secondary: str, scene_start: float, duration: int, emotion: str) -> list[dict]:
    scene_end = scene_start + duration
    character_lines = {
        "Hook": [(primary, "I can explain."), (secondary, "You always say that."), (primary, "This time has context.")],
        "Conflict": [(secondary, "Then explain what everyone just saw."), (primary, "Technically, nobody saw the beginning."), (secondary, "The mud saw everything.")],
        "Escalation": [(primary, "Okay, that looks worse than it is."), (secondary, "It smells worse too."), (primary, "That is a separate issue.")],
        "Twist": [(secondary, "Wait. Why are the crumbs on me?"), (primary, "I was hoping you would not notice."), (secondary, "I notice professionally.")],
        "Payoff": [(primary, "So we are both innocent?"), (secondary, "No. We are both caught."), (primary, "That feels unfairly accurate.")],
    }
    lines = [
        {
            "speaker_id": "narrator",
            "line": narration,
            "emotion": emotion,
            "start": round(scene_start, 2),
            "end": round(min(scene_start + max(1.0, duration * 0.35), scene_end), 2),
        }
    ]
    character_start = lines[0]["end"]
    character_duration = max(0.6, (scene_end - character_start) / 3)
    for offset, (speaker_id, line) in enumerate(character_lines.get(beat, [(primary, "Wait. Did that just happen?")])):
        start = character_start + (offset * character_duration)
        end = scene_end if offset == 2 else min(scene_end, start + character_duration)
        lines.append(
            {
                "speaker_id": speaker_id,
                "line": line,
                "emotion": emotion,
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
    return lines


def _ensure_story_minimums(scenes: list[dict], primary: str, secondary: str) -> list[dict]:
    line_count = sum(len(scene.get("dialogue", [])) for scene in scenes)
    scene_index = 0
    while line_count < 20 and scenes:
        scene = scenes[scene_index % len(scenes)]
        speaker_id = primary if line_count % 2 == 0 else secondary
        scene_end = _time_range_end(str(scene.get("time", ""))) or float(scene.get("duration", 0) or 0)
        scene.setdefault("dialogue", []).append(
            {
                "speaker_id": speaker_id,
                "line": "Wait, that changes everything.",
                "emotion": scene.get("emotion", "surprised"),
                "start": round(max(0.0, scene_end - 0.8), 2),
                "end": round(scene_end, 2),
            }
        )
        line_count += 1
        scene_index += 1

    total_duration = sum(float(scene.get("duration", 0) or 0) for scene in scenes)
    if scenes and total_duration < 25:
        deficit = 25 - total_duration
        scenes[-1]["duration"] = round(float(scenes[-1].get("duration", 0) or 0) + deficit, 2)
        start = _time_range_start(str(scenes[-1].get("time", "")))
        scenes[-1]["time"] = f"{int(start)}-{int(start + scenes[-1]['duration'])}s"
    return scenes


def _time_range_start(value: str) -> float:
    match = re.match(r"(\d+(?:\.\d+)?)", value or "")
    return float(match.group(1)) if match else 0.0


def _time_range_end(value: str) -> float:
    match = re.search(r"-(\d+(?:\.\d+)?)s?$", value or "")
    return float(match.group(1)) if match else 0.0


def _minimax_scene_prompt(*, visual_action: str, character_text: str, environment: str, camera: str, emotion: str, style: str) -> str:
    return (
        f"{visual_action}. Environment: {environment}. Characters with exact recurring design and personality: {character_text}. "
        f"Emotional state: {emotion}. Camera direction: {camera}. "
        f"Style: {style}. Keep identical face shape, clothing, colors, species, proportions, and accessories across every scene. "
        "Vertical 9:16 animated short film frame, readable silhouettes, no captions or on-screen text."
    )


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
