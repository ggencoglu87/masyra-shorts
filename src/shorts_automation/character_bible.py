from __future__ import annotations

import hashlib
import json
from pathlib import Path


STYLE_REFERENCE = "feature-quality cinematic 3D animated series, expressive characters, high detail, soft cinematic lighting, consistent character design"

V7_UNIVERSES = {
    "farm_chaos": {
        "id": "farm_chaos",
        "name": "Farm Chaos",
        "description": "A recurring animated comedy universe where farm animals cause tiny disasters that spiral into clever payoffs.",
        "environment": "sunny stylized farmyard, red barn, hay bales, chicken coop, muddy paths, warm morning light",
        "tone": "chaotic family comedy with expressive animal acting",
    },
    "forest_legends": {
        "id": "forest_legends",
        "name": "Forest Legends",
        "description": "A mysterious forest anthology with recurring creatures, spooky legends, and emotional reveals.",
        "environment": "enchanted deep forest, mossy stones, glowing mushrooms, fog, moonbeams through tall trees",
        "tone": "magical suspense with wonder and danger",
    },
    "space_academy": {
        "id": "space_academy",
        "name": "Space Academy",
        "description": "A colorful sci-fi school where young cadets solve cosmic problems before the bell rings.",
        "environment": "bright orbital academy, glass corridors, starfield windows, floating lockers, training simulator rooms",
        "tone": "high-energy sci-fi adventure comedy",
    },
    "funny_pets": {
        "id": "funny_pets",
        "name": "Funny Pets",
        "description": "A cozy apartment sitcom universe where pets misunderstand human life and create absurd trouble.",
        "environment": "cozy modern apartment, sofa, kitchen island, pet toys, sunlit windows, warm indoor lighting",
        "tone": "fast physical comedy with cute emotional reactions",
    },
    "monster_school": {
        "id": "monster_school",
        "name": "Monster School",
        "description": "A supernatural school series where young monsters learn scary lessons and accidentally become friends.",
        "environment": "friendly gothic school, stone hallways, glowing lockers, classroom cauldrons, stormy windows",
        "tone": "spooky comedy with heart",
    },
}

UNIVERSE_BY_CATEGORY = {
    "Funny Animals": "farm_chaos",
    "Funny Kids": "funny_pets",
    "Funny Fails": "funny_pets",
    "Horror Stories": "monster_school",
    "Reddit Stories": "space_academy",
    "Sports Drama": "space_academy",
    "Relationship Stories": "forest_legends",
    "Minecraft Stories": "monster_school",
    "Motivational Stories": "forest_legends",
    "Celebrity Drama": "space_academy",
    "Survival Stories": "forest_legends",
    "Crazy Facts": "space_academy",
}


def build_character_bible(category: str) -> dict:
    universe = universe_for_category(category)
    characters = _characters_for_category(category)
    for character in characters:
        relationship_text = "; ".join(f"{other}: {detail}" for other, detail in character.get("relationships", {}).items())
        history_text = " ".join(character.get("history", []))
        visual = (
            f"{character['appearance']}; personality: {character['personality']}; "
            f"relationships: {relationship_text}; history: {history_text}; role: {character['role']}"
        )
        character["visual_description"] = visual
        character["style_reference"] = STYLE_REFERENCE
        character["appearance_hash"] = hashlib.sha256(visual.encode("utf-8")).hexdigest()[:16]
        character.setdefault("voice", voice_for_category(category))
        character.setdefault("voice_profile", voice_profile_for_character(character, category))
        character.setdefault("memory", [])
        character["universe"] = universe["id"]
    return {
        "universe": universe,
        "style": STYLE_REFERENCE,
        "narrator_voice_profile": narrator_voice_profile(category),
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


def universe_for_category(category: str) -> dict:
    universe_id = UNIVERSE_BY_CATEGORY.get(category, _slug(category or "Custom"))
    universe = V7_UNIVERSES.get(
        universe_id,
        {
            "id": universe_id,
            "name": category or "Custom",
            "description": f"Recurring AI animated short-film universe for {category or 'custom'} stories.",
            "environment": "stylized cinematic animated short-film set, expressive props, clear staging, vertical frame",
            "tone": "character-first animated comedy drama",
        },
    )
    return {**universe, "visual_style": STYLE_REFERENCE}


def voice_for_category(category: str) -> str:
    voices = {
        "Funny Animals": "energetic animated comedy narrator",
        "Funny Kids": "warm playful narrator",
        "Funny Fails": "fast chaotic comedy narrator",
        "Horror Stories": "slow suspense narrator",
        "Reddit Stories": "confessional story narrator",
        "Sports Drama": "excited commentator",
        "Relationship Stories": "dramatic storyteller",
        "Minecraft Stories": "fast gamer narrator",
        "Motivational Stories": "inspiring narrator",
        "Celebrity Drama": "entertainment host narrator",
        "Survival Stories": "urgent documentary narrator",
        "Crazy Facts": "excited fact narrator",
    }
    return voices.get(category, "cinematic story narrator")


def narrator_voice_profile(category: str) -> dict:
    return {
        "voice_id": "narrator_main",
        "provider": "auto",
        "gender": "neutral",
        "tone": "warm cinematic",
        "gender_tone": "neutral warm narrator",
        "speaking_style": voice_for_category(category),
        "emotion_range": "curious, cinematic, playful, suspenseful when needed",
        "sample_line": "Nobody expected what happened next.",
        "google_voice_name": "Puck",
        "piper_model_env": "PIPER_MODEL_PATH_NARRATOR_MAIN",
    }


def voice_profile_for_character(character: dict, category: str) -> dict:
    species = str(character.get("species", "character")).lower()
    personality = str(character.get("personality", "expressive")).lower()
    if "chicken" in species:
        tone = "male raspy comic rival"
        gender = "male"
        style = "fast sarcastic squawks with sharp timing"
        sample = "Then explain the fish on your face."
        google_voice = "Fenrir"
    elif "cat" in species:
        tone = "male theatrical comedy"
        gender = "male"
        style = "dramatic overconfident excuses with quick panic"
        sample = "I can explain."
        google_voice = "Puck"
    elif "pug" in species:
        tone = "small nervous comic"
        gender = "neutral"
        style = "breathy guilty energy with cute panic"
        sample = "I was only checking if it was safe."
        google_voice = "Kore"
    elif "robot" in species:
        tone = "bright synthetic sidekick"
        gender = "neutral"
        style = "precise anxious beeps with fast delivery"
        sample = "Risk level is now extremely embarrassing."
        google_voice = "Charon"
    elif "ghost" in species:
        tone = "female mischievous airy"
        gender = "female"
        style = "playful spooky confidence"
        sample = "Relax. It only screams during quizzes."
        google_voice = "Leda"
    else:
        tone = "expressive animated character"
        gender = "neutral"
        style = f"{personality} animated dialogue"
        sample = "Wait. Did anyone else see that?"
        google_voice = "Aoede"
    voice_id = str(character.get("id", "character_voice"))
    return {
        "voice_id": voice_id,
        "provider": "auto",
        "gender": gender,
        "tone": tone,
        "gender_tone": tone,
        "speaking_style": style,
        "emotion_range": "neutral, curious, worried, excited, surprised, relieved",
        "sample_line": sample,
        "google_voice_name": google_voice,
        "piper_model_env": f"PIPER_MODEL_PATH_{_slug(voice_id).upper()}",
    }


def _characters_for_category(category: str) -> list[dict]:
    universe_id = UNIVERSE_BY_CATEGORY.get(category, _slug(category or "Custom"))
    if universe_id == "farm_chaos":
        return [
            {
                "id": "bob_cat",
                "name": "Bob",
                "species": "orange tabby cat",
                "appearance": "orange tabby cat, green eyes, red baseball cap, small scar on left ear",
                "personality": "overconfident, dramatic, funny, unlucky",
                "relationships": {"carl_chicken": "rival who always catches Bob pretending nothing happened"},
                "history": ["Bob once got caught stealing fish and has been trying to rebuild his reputation."],
                "memory": ["Always acts innocent when guilty."],
                "role": "main character",
            },
            {
                "id": "carl_chicken",
                "name": "Carl",
                "species": "white chicken",
                "appearance": "white chicken, blue scarf, tiny angry eyebrows",
                "personality": "sarcastic, clever, annoying",
                "relationships": {"bob_cat": "competitive farm rival and accidental comedy partner"},
                "history": ["Carl keeps a mental list of every prank Bob has tried."],
                "memory": ["Usually notices the clue everyone else misses."],
                "role": "rival",
            },
        ]
    if universe_id == "monster_school":
        return [
            {
                "id": "milo_mimic",
                "name": "Milo",
                "species": "young mimic monster",
                "appearance": "small blue mimic monster, round amber eyes, oversized purple hoodie, tiny horns, nervous smile",
                "personality": "curious, anxious, secretly brave",
                "relationships": {"nora_ghost": "best friend who pushes Milo into spooky adventures"},
                "history": ["Milo failed Scaring 101 because he apologized to everyone he startled."],
                "memory": ["Tries to solve scary problems with kindness first."],
                "role": "main character",
            },
            {
                "id": "nora_ghost",
                "name": "Nora",
                "species": "young ghost",
                "appearance": "transparent lavender ghost girl, silver bob haircut, star-shaped glasses, floating scarf",
                "personality": "bold, mischievous, loyal",
                "relationships": {"milo_mimic": "protective best friend and chaos coach"},
                "history": ["Nora knows every secret tunnel in Monster School."],
                "memory": ["Makes jokes when danger gets too serious."],
                "role": "best friend",
            },
        ]
    if universe_id == "space_academy":
        return [
            {
                "id": "nova_cadet",
                "name": "Nova",
                "species": "human space cadet",
                "appearance": "teen space cadet, copper curls, teal flight jacket, glowing academy badge, silver boots",
                "personality": "inventive, stubborn, optimistic",
                "relationships": {"zip_robot": "tiny robot teammate who calculates trouble too late"},
                "history": ["Nova once saved the cafeteria from zero-gravity soup."],
                "memory": ["Trusts instinct before protocol."],
                "role": "main character",
            },
            {
                "id": "zip_robot",
                "name": "Zip",
                "species": "tiny floating robot",
                "appearance": "small round yellow robot, single blue camera eye, retractable arms, sticker-covered shell",
                "personality": "logical, panicky, accidentally funny",
                "relationships": {"nova_cadet": "loyal sidekick who follows Nova into bad ideas"},
                "history": ["Zip keeps a database of every academy rule Nova has bent."],
                "memory": ["Announces risk percentages at the worst possible moment."],
                "role": "sidekick",
            },
        ]
    if universe_id == "funny_pets":
        return [
            {
                "id": "pixel_pug",
                "name": "Pixel",
                "species": "pug",
                "appearance": "tiny tan pug, huge glossy eyes, green bow tie, one floppy ear, round belly",
                "personality": "dramatic, food-obsessed, innocent-looking",
                "relationships": {"miso_cat": "roommate rival who knows Pixel's snack secrets"},
                "history": ["Pixel once blamed a vacuum cleaner for eating snacks."],
                "memory": ["Panics whenever evidence points at him."],
                "role": "main character",
            },
            {
                "id": "miso_cat",
                "name": "Miso",
                "species": "gray cat",
                "appearance": "sleek gray cat, yellow eyes, pink collar bell, white socks, unimpressed face",
                "personality": "calm, sarcastic, brilliant",
                "relationships": {"pixel_pug": "chaotic roommate and favorite mystery to solve"},
                "history": ["Miso has solved three apartment mysteries without standing up."],
                "memory": ["Uses silence as a weapon."],
                "role": "detective roommate",
            },
        ]
    if universe_id == "forest_legends":
        return [
            {
                "id": "willow_fox",
                "name": "Willow",
                "species": "red fox",
                "appearance": "red fox with white-tipped tail, emerald cloak, leaf-shaped pendant, bright amber eyes",
                "personality": "clever, kind, impulsive",
                "relationships": {"bramble_bear": "gentle protector and reluctant adventure partner"},
                "history": ["Willow once woke an ancient tree by telling it a joke."],
                "memory": ["Runs toward mysteries before checking the map."],
                "role": "main character",
            },
            {
                "id": "bramble_bear",
                "name": "Bramble",
                "species": "young bear",
                "appearance": "round brown bear cub, moss-green satchel, tiny wooden flute, cream muzzle",
                "personality": "careful, loyal, easily amazed",
                "relationships": {"willow_fox": "best friend who keeps him brave"},
                "history": ["Bramble remembers every forest legend his grandmother told him."],
                "memory": ["Hums when nervous."],
                "role": "best friend",
            },
        ]
    return [
        {
            "id": "alex_main",
            "name": "Alex",
            "species": "human",
            "appearance": "expressive young adult, teal jacket, dark hair, bright eyes, cinematic animated face",
            "personality": "curious, emotional, impulsive",
            "relationships": {"riley_friend": "trusted friend and honest critic"},
            "history": ["Alex keeps getting pulled into strange short-film problems."],
            "memory": ["Learns by making one bold mistake first."],
            "role": "main character",
        },
        {
            "id": "riley_friend",
            "name": "Riley",
            "species": "human",
            "appearance": "supporting friend, purple hoodie, round glasses, warm smile",
            "personality": "clever, skeptical, loyal",
            "relationships": {"alex_main": "loyal friend who sees the twist coming early"},
            "history": ["Riley has saved Alex from three bad plans."],
            "memory": ["Asks the question everyone else avoids."],
            "role": "supporting character",
        },
    ]


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_") or "custom"
