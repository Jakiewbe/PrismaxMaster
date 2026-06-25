from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any


class JsonlLogger:
    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict[str, Any]) -> None:
        output = dict(record)
        output.setdefault("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n")

    def write_error(self, error: BaseException, context: dict[str, Any] | None = None) -> None:
        self.write({
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
            "context": context or {},
        })

