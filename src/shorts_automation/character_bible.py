from __future__ import annotations

import hashlib
import json
from pathlib import Path


STYLE_REFERENCE = "cinematic 3D animated movie, expressive characters, high detail, soft cinematic lighting, consistent character design"


def build_character_bible(category: str) -> dict:
    characters = _characters_for_category(category)
    for character in characters:
        visual = f"{character['appearance']}; personality: {character['personality']}; role: {character['role']}"
        character["visual_description"] = visual
        character["style_reference"] = STYLE_REFERENCE
        character["appearance_hash"] = hashlib.sha256(visual.encode("utf-8")).hexdigest()[:16]
    return {
        "style": STYLE_REFERENCE,
        "consistency_rules": [
            "Use the exact same character ids and appearance in every scene.",
            "Do not change clothing, colors, species, face shape, or accessories between scenes.",
            "Every image and video prompt must include the character appearance text.",
        ],
        "characters": characters,
    }


def write_character_bible(video_dir: Path, category: str) -> dict:
    bible = build_character_bible(category)
    (video_dir / "character_bible.json").write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    return bible


def load_character_bible(video_dir: Path) -> dict:
    path = video_dir / "character_bible.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def character_prompt_text(bible: dict, character_ids: list[str] | None = None) -> str:
    selected = []
    allowed = set(character_ids or [])
    for character in bible.get("characters", []):
        if not allowed or character.get("id") in allowed:
            selected.append(f"{character['id']}: {character['visual_description']}")
    return " | ".join(selected)


def _characters_for_category(category: str) -> list[dict]:
    if category == "Funny Animals":
        return [
            {
                "id": "bob_cat",
                "name": "Bob",
                "species": "orange tabby cat",
                "appearance": "orange tabby cat, green eyes, red baseball cap, small scar on left ear",
                "personality": "overconfident, dramatic, funny, unlucky",
                "role": "main character",
            },
            {
                "id": "carl_chicken",
                "name": "Carl",
                "species": "white chicken",
                "appearance": "white chicken, blue scarf, tiny angry eyebrows",
                "personality": "sarcastic, clever, annoying",
                "role": "rival",
            },
        ]
    if category == "Horror Stories":
        return [
            {
                "id": "eli_boy",
                "name": "Eli",
                "species": "human boy",
                "appearance": "12-year-old boy, curly black hair, yellow hoodie, worried brown eyes",
                "personality": "curious, brave, nervous",
                "role": "main character",
            },
            {
                "id": "shadow_visitor",
                "name": "The Visitor",
                "species": "shadow figure",
                "appearance": "tall smoky shadow figure, long fingers, faint glowing eyes, no clear face",
                "personality": "silent, mysterious, unsettling",
                "role": "threat",
            },
        ]
    if category == "Sports Drama":
        return [
            {
                "id": "jay_rookie",
                "name": "Jay",
                "species": "human athlete",
                "appearance": "young basketball player, blue jersey number 12, short curls, white wristband",
                "personality": "quiet, determined, underestimated",
                "role": "main character",
            },
            {
                "id": "coach_mara",
                "name": "Coach Mara",
                "species": "human coach",
                "appearance": "middle-aged coach, black tracksuit, silver whistle, intense eyes",
                "personality": "tough, strategic, protective",
                "role": "mentor",
            },
        ]
    return [
        {
            "id": "alex_main",
            "name": "Alex",
            "species": "human",
            "appearance": "expressive young adult, teal jacket, dark hair, bright eyes, cinematic animated face",
            "personality": "curious, emotional, impulsive",
            "role": "main character",
        },
        {
            "id": "riley_friend",
            "name": "Riley",
            "species": "human",
            "appearance": "supporting friend, purple hoodie, round glasses, warm smile",
            "personality": "clever, skeptical, loyal",
            "role": "supporting character",
        },
    ]
