from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def ensure_learning_db(output_dir: Path) -> Path:
    path = output_dir / "learning.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS video_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_dir TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                channel_target TEXT NOT NULL,
                hook TEXT,
                format_signature TEXT,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                completion_rate REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS episode_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_dir TEXT UNIQUE NOT NULL,
                universe TEXT NOT NULL,
                title TEXT,
                characters TEXT,
                relationships TEXT,
                story_arcs TEXT,
                recurring_jokes TEXT,
                character_growth TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    return path


def record_generated_package(video_dir: Path, plan: dict, learning_db: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    category = plan.get("trend", {}).get("category", "")
    channel_target = plan.get("channel_target", "")
    hook = plan.get("content_strategy", {}).get("hook", "")
    format_signature = f"{category}:{plan.get('voice_profile', {}).get('style', '')}:{hook[:40]}"
    universe = plan.get("universe", {}).get("id") or category.lower().replace(" ", "_")
    characters = ",".join(character.get("id", "") for character in plan.get("character_bible", {}).get("characters", []) if character.get("id"))
    story_arc = plan.get("content_strategy", {}).get("story_structure", "")
    recurring_jokes = "the guilty pet tries to act normal" if category == "Funny Animals" else ""
    with sqlite3.connect(learning_db) as connection:
        connection.execute(
            """
            INSERT INTO video_results (
                video_dir, category, channel_target, hook, format_signature, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_dir) DO UPDATE SET
                category=excluded.category,
                channel_target=excluded.channel_target,
                hook=excluded.hook,
                format_signature=excluded.format_signature,
                updated_at=excluded.updated_at
            """,
            (str(video_dir), category, channel_target, hook, format_signature, now, now),
        )
        connection.execute(
            """
            INSERT INTO episode_memory (
                video_dir, universe, title, characters, relationships, story_arcs,
                recurring_jokes, character_growth, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_dir) DO UPDATE SET
                universe=excluded.universe,
                title=excluded.title,
                characters=excluded.characters,
                story_arcs=excluded.story_arcs,
                recurring_jokes=excluded.recurring_jokes,
                updated_at=excluded.updated_at
            """,
            (
                str(video_dir),
                universe,
                plan.get("title", ""),
                characters,
                "",
                story_arc,
                recurring_jokes,
                "",
                now,
                now,
            ),
        )
