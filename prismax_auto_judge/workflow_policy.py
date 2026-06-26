from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class DailyWorkflowPolicy:
    """Non-invasive policy for the daily control-then-VLA routine."""

    def __init__(self, config: dict[str, Any], base_dir: str | Path):
        self.config = config
        self.base_dir = Path(base_dir)
        self.workflow = config.get("daily_workflow", {})

    def today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def can_attempt_vla(self) -> tuple[bool, str]:
        if not self.workflow.get("enabled", True):
            return True, "workflow_policy_disabled"

        max_labels = int(self.workflow.get("max_labels_per_day", 4))
        done = self.get_today_label_count()
        if done >= max_labels:
            return False, f"daily_vla_quota_reached:{done}/{max_labels}"

        if self.workflow.get("control_first", True):
            ready, reason = self.is_control_ready()
            if not ready:
                return False, reason

        return True, "ok"

    def get_today_label_count(self) -> int:
        data = self._read_counts()
        item = data.get(self.today(), {})
        return int(item.get("submitted", 0))

    def record_vla_result(self, submitted: bool) -> None:
        data = self._read_counts()
        today = self.today()
        item = data.setdefault(today, {"seen": 0, "submitted": 0})
        item["seen"] = int(item.get("seen", 0)) + 1
        if submitted:
            item["submitted"] = int(item.get("submitted", 0)) + 1
        self._counts_path().write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def is_control_ready(self) -> tuple[bool, str]:
        path = self._resolve_path(self.workflow.get("control_state_file", "../prismax_state.json"))
        if not path.exists():
            if self.workflow.get("block_if_control_state_missing", False):
                return False, f"control_state_missing:{path}"
            return True, "control_state_missing_but_not_blocking"
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return False, f"control_state_unreadable:{exc}"

        min_ops = int(self.workflow.get("min_control_operations_before_vla", 1))
        total_ops = int(state.get("totalOperations", state.get("count", 0)) or 0)
        if total_ops < min_ops:
            return False, f"control_operations_below_threshold:{total_ops}/{min_ops}"
        return True, f"control_ready:{total_ops}/{min_ops}"

    def _read_counts(self) -> dict[str, Any]:
        path = self._counts_path()
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _counts_path(self) -> Path:
        path = self._resolve_path(self.workflow.get("daily_counts_path", "data/logs/vla_daily_counts.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.base_dir / path
