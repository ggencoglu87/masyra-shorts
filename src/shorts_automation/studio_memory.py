from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def studio_dir_for_run(output_root: Path) -> Path:
    return output_root.parent / "studio"


def update_studio_memory(output_root: Path, package_dir: Path, item: dict) -> dict:
    studio_dir = studio_dir_for_run(output_root)
    studio_dir.mkdir(parents=True, exist_ok=True)
    library_path = studio_dir / "character-library.json"
    memory_path = studio_dir / "episode-memory.json"

    library = _read_json(library_path) or {"characters": {}}
    memory = _read_json(memory_path) or {"episodes": [], "universes": {}}

    bible = item.get("character_bible", {})
    universe = bible.get("universe", {})
    universe_id = universe.get("id") or item.get("trend", {}).get("category", "custom").lower().replace(" ", "_")
    now = datetime.now(timezone.utc).isoformat()

    for character in bible.get("characters", []):
        key = character.get("id")
        if not key:
            continue
        existing = library["characters"].get(key, {})
        library["characters"][key] = {
            **existing,
            "id": key,
            "name": character.get("name", ""),
            "appearance": character.get("appearance", ""),
            "appearance_hash": character.get("appearance_hash", ""),
            "voice": character.get("voice", ""),
            "personality": character.get("personality", ""),
            "relationships": {**existing.get("relationships", {}), **character.get("relationships", {})},
            "history": _merge_unique(existing.get("history", []), character.get("history", [])),
            "memory": _merge_unique(existing.get("memory", []), character.get("memory", [])),
            "universe": universe_id,
            "style_reference": character.get("style_reference", ""),
            "updated_at": now,
        }

    universe_memory = memory["universes"].setdefault(
        universe_id,
        {
            "id": universe_id,
            "name": universe.get("name") or universe_id,
            "relationships": [],
            "story_arcs": [],
            "recurring_jokes": [],
            "character_growth": [],
        },
    )
    episode = {
        "video_dir": str(package_dir),
        "title": item.get("title", ""),
        "category": item.get("trend", {}).get("category", ""),
        "universe": universe_id,
        "characters": [character.get("id") for character in bible.get("characters", []) if character.get("id")],
        "hook": item.get("content_strategy", {}).get("hook", ""),
        "conflict": _story_field(item, "conflict"),
        "escalation": _story_field(item, "escalation"),
        "payoff": _story_field(item, "payoff"),
        "story_arc": item.get("content_strategy", {}).get("story_structure", ""),
        "episode_premise": item.get("content_strategy", {}).get("episode_premise", ""),
        "created_at": now,
    }
    memory["episodes"].append(episode)
    universe_memory["story_arcs"] = _merge_unique(universe_memory.get("story_arcs", []), [episode["story_arc"]])
    universe_memory["recurring_jokes"] = _merge_unique(universe_memory.get("recurring_jokes", []), _recurring_jokes(item))
    universe_memory["relationships"] = _merge_unique(universe_memory.get("relationships", []), _relationship_summaries(bible))
    universe_memory["character_growth"] = _merge_unique(universe_memory.get("character_growth", []), _character_growth(item))

    library_path.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
    memory_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"character_library": str(library_path), "episode_memory": str(memory_path)}


def _recurring_jokes(item: dict) -> list[str]:
    category = item.get("trend", {}).get("category", "")
    if category == "Funny Animals":
        return ["the guilty pet tries to act normal"]
    if category == "Minecraft Stories":
        return ["never dig straight down"]
    return []


def _relationship_summaries(bible: dict) -> list[str]:
    summaries = []
    for character in bible.get("characters", []):
        for other, detail in character.get("relationships", {}).items():
            summaries.append(f"{character.get('id')} -> {other}: {detail}")
    return summaries


def _character_growth(item: dict) -> list[str]:
    bible = item.get("character_bible", {})
    payoff = _story_field(item, "payoff")
    return [f"{character.get('id')} episode lesson: {payoff}" for character in bible.get("characters", []) if character.get("id") and payoff]


def _story_field(item: dict, key: str) -> str:
    for scene in item.get("storyboard", []):
        if str(scene.get("beat", "")).lower() == key:
            return str(scene.get("narration", ""))
    return ""


def _merge_unique(existing: list, incoming: list) -> list:
    merged = []
    for value in [*existing, *incoming]:
        if value and value not in merged:
            merged.append(value)
    return merged


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
