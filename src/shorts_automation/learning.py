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
    return path


def record_generated_package(video_dir: Path, plan: dict, learning_db: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    category = plan.get("trend", {}).get("category", "")
    channel_target = plan.get("channel_target", "")
    hook = plan.get("content_strategy", {}).get("hook", "")
    format_signature = f"{category}:{plan.get('voice_profile', {}).get('style', '')}:{hook[:40]}"
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
