from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


VALID_STATUSES = {"Needs Edit", "Approved", "Rejected"}
DEFAULT_STATUS = "Needs Edit"


class StatusStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, video_dir: Path) -> dict:
        data = self._read()
        key = self._key(video_dir)
        return data.get(
            key,
            {
                "status": DEFAULT_STATUS,
                "updated_at": None,
                "notes": "",
            },
        )

    def set(self, video_dir: Path, status: str, notes: str = "") -> dict:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        data = self._read()
        key = self._key(video_dir)
        data[key] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data[key]

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _key(video_dir: Path) -> str:
        return str(video_dir.resolve())
