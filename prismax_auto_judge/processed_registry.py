from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ProcessedRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def is_submitted(self, episode_id: str) -> bool:
        item = self._data.get(episode_id)
        return bool(isinstance(item, dict) and item.get("submitted"))

    def mark(self, episode_id: str, decision: str, submitted: bool) -> None:
        self._data[episode_id] = {
            "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
            "decision": decision,
            "submitted": submitted,
        }
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

