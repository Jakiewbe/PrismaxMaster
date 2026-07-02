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

        max_tasks = self.workflow.get("max_vla_tasks_per_day")
        if max_tasks is not None:
            tasks_done = self.get_today_task_count()
            max_tasks_int = int(max_tasks)
            if tasks_done >= max_tasks_int:
                return False, f"daily_vla_task_quota_reached:{tasks_done}/{max_tasks_int}"

        if self.workflow.get("control_first", True):
            ready, reason = self.is_control_ready()
            if not ready:
                return False, reason

        return True, "ok"

    def get_today_label_count(self) -> int:
        data = self._read_counts()
        item = data.get(self.today(), {})
        return int(item.get("submitted", 0))

    def get_today_task_count(self) -> int:
        data = self._read_counts()
        item = data.get(self.today(), {})
        return int(item.get("tasks_attempted", item.get("tasks", 0)))

    def record_vla_task_result(self, completed: bool, episodes_seen: int, episodes_submitted: int) -> None:
        data = self._read_counts()
        today = self.today()
        item = data.setdefault(today, {"seen": 0, "submitted": 0})
        item["tasks_attempted"] = int(item.get("tasks_attempted", 0)) + 1
        if completed:
            item["tasks_completed"] = int(item.get("tasks_completed", 0)) + 1
        item["task_episode_seen"] = int(item.get("task_episode_seen", 0)) + int(episodes_seen)
        item["task_episode_submitted"] = int(item.get("task_episode_submitted", 0)) + int(episodes_submitted)
        self._counts_path().write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

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

        if self.workflow.get("require_control_idle_before_vla", True):
            idle, idle_reason = self.is_control_idle_for_vla(state)
            if not idle:
                return False, idle_reason

        min_ops = int(self.workflow.get("min_control_operations_before_vla", 1))
        total_ops = int(state.get("totalOperations", state.get("count", 0)) or 0)
        if total_ops >= min_ops:
            return True, f"control_ready:{total_ops}/{min_ops}"

        rank_threshold = self.workflow.get("allow_vla_when_gold_rank_gt")
        rank = self._read_rank(state)
        if rank_threshold is not None and rank is not None:
            threshold = int(rank_threshold)
            if rank > threshold:
                return True, f"control_ready_by_gold_rank:{rank}>{threshold};ops={total_ops}/{min_ops}"

        if rank_threshold is not None:
            return False, f"control_operations_below_threshold:{total_ops}/{min_ops};rank={rank};need_rank_gt:{rank_threshold}"
        return False, f"control_operations_below_threshold:{total_ops}/{min_ops}"

    def is_control_idle_for_vla(self, state: dict[str, Any]) -> tuple[bool, str]:
        if bool(state.get("isOperating")):
            return False, "control_not_idle_for_vla:isOperating"
        if bool(state.get("isQueuing")):
            return False, "control_not_idle_for_vla:isQueuing"
        if bool(state.get("walletPopupActive")):
            return False, "control_not_idle_for_vla:walletPopupActive"
        owner = state.get("actionLockOwner")
        if owner:
            return False, f"control_not_idle_for_vla:actionLockOwner={owner}"
        return True, "control_idle_for_vla"

    def _read_rank(self, state: dict[str, Any]) -> int | None:
        for key in ("goldRank", "trainingGoldRank"):
            value = state.get(key)
            parsed = self._parse_int(value)
            if parsed is not None:
                return parsed

        if not self._is_gold_arm_state(state):
            return None

        for key in ("rank", "lastRank"):
            value = state.get(key)
            parsed = self._parse_int(value)
            if parsed is not None:
                return parsed
        return None

    def _is_gold_arm_state(self, state: dict[str, Any]) -> bool:
        gold_label = str(self.workflow.get("gold_arm_label", "Training Arm Gold")).strip().lower()
        for key in ("currentArm", "current_arm", "arm", "armLabel", "queuedArm", "activeArm"):
            value = state.get(key)
            if value is None:
                continue
            if str(value).strip().lower() == gold_label:
                return True
        return False

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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

